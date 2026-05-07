from __future__ import annotations

from openai import OpenAI
import logging
import os
import threading
from pathlib import Path
from typing import Any

from system_prompt.system_prompt import build_request_system_prompt, build_system_prompt
from agent.context_compaction import compact_context_references
from agent.agent_metrics import AgentMetrics, estimate_messages_chars
from agent.agent_skill_policy import (
    reset_skill_state,
    set_skill_state_from_selection,
    validate_final_response_against_skill_policy,
)
from agent.agent_tool_execution import execute_tool_call
from agent.model_streaming import consume_model_stream
from agent.run_trace import RunTrace
from tools.tools import OPENAI_TOOLS
from config import SETTINGS
from skills.skills import record_skill_event, request_skill_for_intent
from skills.intent import extract_intent

logger = logging.getLogger(__name__)


class Agent:
    def __init__(self):
        self.BASE_DIR = SETTINGS.sandbox_dir
        self.MAX_AUTO_TURNS = SETTINGS.max_auto_turns
        self.DONE = getattr(SETTINGS, 'done_token', '__DONE__')

        os.makedirs(self.BASE_DIR, exist_ok=True)

        self.client = OpenAI(base_url=SETTINGS.base_url, api_key=SETTINGS.api_key)
        self.model = SETTINGS.model_name
        self.lock = threading.RLock()
        self.messages = self._initial_messages()
        self.tool_events: list[dict[str, object]] = []
        self.is_generating = False
        self.last_error = ''
        self.loop_turn = 0
        self.on_stream = None
        self.run_id = 0
        self.active_skill_name: str | None = None
        self.active_skill_policy: dict[str, Any] = {}
        self.active_skill_selection: dict[str, Any] | None = None
        self.request_system_prompt: str | None = None
        self.skill_creation_failures = 0
        self.skill_tool_call_index = 0
        self.verified_symbols_by_path: dict[str, set[str]] = {}
        self.owasp_reference_search_count = 0
        self.metrics = AgentMetrics()
        self.run_trace: RunTrace | None = None
        self.pending_approval: dict[str, Any] | None = None
        self.last_fulfilled_skill_name: str | None = None

    def _initial_messages(self):
        return [{'role': 'system', 'content': build_system_prompt()}]

    def _reset_skill_state(self) -> None:
        reset_skill_state(self)
        self.active_skill_selection = None
        self.request_system_prompt = None
        self.skill_creation_failures = 0

    def _set_skill_state_from_selection(self, result: dict[str, Any]) -> None:
        set_skill_state_from_selection(self, result)

    def _is_current_run(self, run_id: int) -> bool:
        return run_id == self.run_id

    def reset(self) -> bool:
        with self.lock:
            if self.is_generating:
                return False

            self.run_id += 1
            self.messages = self._initial_messages()
            self.tool_events = []
            self.last_error = ''
            self.loop_turn = 0
            self.pending_approval = None
            self.last_fulfilled_skill_name = None
            self._reset_skill_state()
            self.metrics.reset_current()

        self._notify_stream()
        return True

    def add_message(self, submitted) -> None:
        with self.lock:
            self._append_message_locked(submitted)

    def _append_message_locked(self, submitted: dict[str, Any]) -> None:
        self.messages.append(submitted)
        if submitted.get('role') == 'user':
            self.tool_events = []
            self.pending_approval = None
            self._reset_skill_state()

    def snapshot_messages(self) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(message) for message in self.messages]

    def snapshot_tool_events(self) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(event) for event in self.tool_events]

    def snapshot_runtime_metrics(self) -> dict[str, object]:
        with self.lock:
            return self.metrics.snapshot()

    def snapshot_pending_approval(self) -> dict[str, Any] | None:
        with self.lock:
            return dict(self.pending_approval) if self.pending_approval else None

    def set_pending_approval(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> None:
        with self.lock:
            self.pending_approval = {
                'tool': tool_name,
                'call_id': call_id,
                'args': dict(args),
                'approval_id': result.get('approval_id'),
                'domain': result.get('domain'),
                'url': result.get('url') or args.get('url'),
            }

    def replace_pending_approval(
        self,
        previous_approval_id: str | None,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> bool:
        with self.lock:
            if not self.pending_approval:
                return False
            if previous_approval_id is not None and self.pending_approval.get('approval_id') != previous_approval_id:
                return False
            self.pending_approval = {
                'tool': tool_name,
                'call_id': call_id,
                'args': dict(args),
                'approval_id': result.get('approval_id'),
                'domain': result.get('domain'),
                'url': result.get('url') or args.get('url'),
            }
            self.last_error = 'Waiting for user approval.'
            return True

    def clear_pending_approval(self, approval_id: str | None = None) -> dict[str, Any] | None:
        with self.lock:
            if not self.pending_approval:
                return None
            if approval_id is not None and self.pending_approval.get('approval_id') != approval_id:
                return None
            pending = dict(self.pending_approval)
            self.pending_approval = None
            if self.last_error == 'Waiting for user approval.':
                self.last_error = ''
            return pending

    def is_busy(self) -> bool:
        with self.lock:
            return self.is_generating

    def _notify_stream(self):
        callback = self.on_stream
        if callback is not None:
            try:
                callback()
            except Exception:
                logger.exception('stream notification callback failed')

    def _trace(self, event: str, **fields: Any) -> None:
        trace = self.run_trace
        if trace is not None:
            trace.record(event, **fields)

    def reserve_generation(self, submitted: dict[str, Any] | None = None) -> int | None:
        with self.lock:
            if self.is_generating:
                return None
            if submitted is not None:
                self._append_message_locked(submitted)
            self.is_generating = True
            self.last_error = ''
            self.loop_turn = 0
            self.run_id += 1
            current_run_id = self.run_id
            system_prompt = str(self.messages[0].get('content', '')) if self.messages else ''
            self.metrics.start_request(current_run_id, self.model, len(system_prompt))
            self.run_trace = RunTrace.start(current_run_id)
            latest_user = self._latest_user_text()
            self._trace(
                'run_started',
                model=self.model,
                system_prompt_chars=len(system_prompt),
                user_message=self.run_trace.payload(latest_user) if self.run_trace else latest_user,
            )
        self._notify_stream()
        return current_run_id

    def _start_generation(self) -> int | None:
        return self.reserve_generation()

    def _finish_generation(self, run_id: int):
        with self.lock:
            if not self._is_current_run(run_id):
                return
            self.is_generating = False
            self.metrics.finish_request(run_id)
            last_error = self.last_error
            metrics = self.metrics.snapshot().get('last_request')
            self._trace('run_finished', last_error=last_error, metrics=metrics)
            self.run_trace = None
        self._notify_stream()

    def _normalize_message_for_api(self, message: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {'role': message['role']}

        if 'content' in message:
            payload['content'] = message['content']

        if message.get('role') == 'assistant' and message.get('tool_calls'):
            payload['tool_calls'] = message['tool_calls']
            payload['content'] = message.get('content')

        if message.get('role') == 'tool':
            payload['tool_call_id'] = message['tool_call_id']
            payload['content'] = message.get('content', '')

        return payload

    def _latest_user_text(self) -> str:
        with self.lock:
            for message in reversed(self.messages):
                if message.get('role') == 'user':
                    content = message.get('content')
                    if isinstance(content, str):
                        return content
        return ''

    def _skill_selection_text_for_latest_user(self) -> str:
        user_text = self._latest_user_text().strip()
        if self.last_fulfilled_skill_name != 'owasp_security_review':
            return user_text

        intent = extract_intent(user_text)
        path = intent.get('args', {}).get('path')
        tokens = intent.get('tokens') or set()
        action = intent.get('action')
        if not isinstance(path, str) or not path:
            return user_text
        if action != 'review' and 'review' not in tokens and 'audit' not in tokens and 'inspect' not in tokens:
            return user_text
        if tokens & {'security', 'owasp', 'vulnerability', 'vulnerabilities', 'appsec'}:
            return user_text

        name = Path(path).name.lower()
        if name.startswith('security_') or name.startswith('security-'):
            return f'OWASP security review {path}'
        if user_text.lower().strip().startswith(('now review ', 'review ', 'audit ', 'inspect ')):
            return f'OWASP security review {path}'

        return user_text

    def _prepare_model_call(self, run_id: int) -> tuple[list[dict[str, Any]], int, int | None] | None:
        with self.lock:
            if not self._is_current_run(run_id):
                return None
            request_messages = [self._normalize_message_for_api(dict(message)) for message in self.messages]
            if request_messages and self.request_system_prompt:
                request_messages[0]['content'] = self.request_system_prompt
            turn_index = self.loop_turn
            uncompacted_prompt_chars = estimate_messages_chars(request_messages)
            request_messages, compaction_stats = compact_context_references(request_messages)
            prompt_chars = estimate_messages_chars(request_messages)
            model_call_index = self.metrics.start_model_call(
                run_id,
                turn_index,
                self.model,
                prompt_chars,
                uncompacted_prompt_chars=uncompacted_prompt_chars,
                compaction_stats=compaction_stats,
            )
            if compaction_stats.get('context_reference_count'):
                self._trace(
                    'context_compaction_applied',
                    turn=turn_index,
                    original_prompt_chars=uncompacted_prompt_chars,
                    compacted_prompt_chars=prompt_chars,
                    saved_chars=compaction_stats.get('context_reference_saved_chars'),
                    reference_count=compaction_stats.get('context_reference_count'),
                    source_count=compaction_stats.get('context_reference_source_count'),
                    aliases=compaction_stats.get('context_reference_aliases'),
                    transforms=compaction_stats.get('context_reference_transforms'),
                )
            self._trace(
                'model_call_started',
                turn=turn_index,
                model=self.model,
                prompt_chars=prompt_chars,
                uncompacted_prompt_chars=uncompacted_prompt_chars,
                context_reference_saved_chars=compaction_stats.get('context_reference_saved_chars'),
                context_reference_count=compaction_stats.get('context_reference_count'),
                messages=self.run_trace.payload(request_messages) if self.run_trace else request_messages,
            )

        return request_messages, turn_index, model_call_index

    def _append_assistant_placeholder(self, run_id: int) -> dict[str, Any] | None:
        with self.lock:
            if not self._is_current_run(run_id):
                return None
            assistant_message: dict[str, Any] = {'role': 'assistant', 'content': ''}
            self.messages.append(assistant_message)

        self._notify_stream()
        return assistant_message

    def _finish_model_call(
        self,
        run_id: int,
        model_call_index: int | None,
        turn_index: int,
        assistant_message: dict[str, Any],
    ) -> dict[str, Any] | None:
        with self.lock:
            if not self._is_current_run(run_id):
                return None
            if assistant_message.get('tool_calls') and not assistant_message.get('content'):
                assistant_message['content'] = ''
            self.metrics.finish_model_call(run_id, model_call_index)
            self._trace(
                'model_call_finished',
                turn=turn_index,
                assistant_message=self.run_trace.payload(assistant_message) if self.run_trace else assistant_message,
            )

        self._notify_stream()
        return dict(assistant_message)

    def _fail_model_call(
        self,
        run_id: int,
        model_call_index: int | None,
        turn_index: int,
        assistant_message: dict[str, Any],
        exc: Exception,
    ) -> dict[str, Any] | None:
        error_text = f'[Error: {exc}]'
        with self.lock:
            if not self._is_current_run(run_id):
                return None
            assistant_message.clear()
            assistant_message.update({'role': 'assistant', 'content': error_text})
            self.last_error = str(exc)
            self.metrics.finish_model_call(run_id, model_call_index)
            self._trace('model_call_failed', turn=turn_index, error=str(exc))

        self._notify_stream()
        return {'role': 'assistant', 'content': error_text}

    def _select_skill_for_current_request(self) -> dict[str, Any] | None:
        user_text = self._latest_user_text().strip()
        if not user_text:
            return None
        selection_text = self._skill_selection_text_for_latest_user()

        try:
            self._trace('skill_selection_started', user_message=user_text, selection_text=selection_text)
            result = request_skill_for_intent(selection_text)
        except Exception as exc:
            with self.lock:
                self.tool_events.append({
                    'kind': 'skill_selection',
                    'status': 'error',
                    'error': str(exc),
                })
                self._trace('skill_selection_failed', error=str(exc))
            return None

        with self.lock:
            self.tool_events.append({
                'kind': 'skill_selection',
                'status': result.get('status'),
                'skill_name': result.get('skill_name'),
                'selection': result.get('selection'),
            })
            self._trace(
                'skill_selection_finished',
                status=result.get('status'),
                skill_name=result.get('skill_name'),
                result=self.run_trace.payload(result) if self.run_trace else result,
            )

        if result.get('status') != 'ok' or not result.get('skill_name'):
            return None
        return result

    def _configure_request_skill(
        self,
        run_id: int,
        selected_skill: dict[str, Any] | None,
    ) -> bool:
        with self.lock:
            if not self._is_current_run(run_id):
                return False
            self.active_skill_selection = selected_skill
            self._set_skill_state_from_selection(selected_skill or {})
            base_prompt = str(self.messages[0].get('content', '')) if self.messages else ''
            self.request_system_prompt = build_request_system_prompt(base_prompt, selected_skill)
            if self.metrics.current_request:
                self.metrics.current_request['estimated_system_prompt_chars'] = len(self.request_system_prompt)
            self._trace(
                'request_system_prompt_built',
                active_skill_name=self.active_skill_name,
                active_skill_selection=(
                    self.run_trace.payload(self.active_skill_selection)
                    if self.run_trace
                    else self.active_skill_selection
                ),
                system_prompt_chars=len(self.request_system_prompt),
                system_prompt=self.run_trace.payload(self.request_system_prompt) if self.run_trace else self.request_system_prompt,
            )

        return True

    def _call_model_once(self, run_id: int) -> dict[str, Any] | None:
        prepared = self._prepare_model_call(run_id)
        if prepared is None:
            return None
        request_messages, turn_index, model_call_index = prepared

        assistant_message = self._append_assistant_placeholder(run_id)
        if assistant_message is None:
            return None

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=request_messages,
                tools=OPENAI_TOOLS,
                temperature=0.1,
                stream=True,
            )

            if not consume_model_stream(self, stream, run_id, model_call_index, assistant_message):
                return None
            return self._finish_model_call(run_id, model_call_index, turn_index, assistant_message)

        except Exception as exc:
            return self._fail_model_call(run_id, model_call_index, turn_index, assistant_message, exc)

    def _execute_callable(self, tool_call: dict[str, Any], run_id: int) -> bool:
        return execute_tool_call(self, tool_call, run_id)

    def _handle_skill_policy_blocked_final_response(
        self,
        run_id: int,
        content: str,
        policy_error: dict[str, Any],
    ) -> bool:
        with self.lock:
            if not self._is_current_run(run_id):
                return False
            if self.messages and self.messages[-1].get('role') == 'assistant':
                self.messages.pop()
            self.messages.append({
                'role': 'system',
                'content': (
                    'Runtime skill policy blocked the previous final answer.\n'
                    f'{policy_error["message"]}\n'
                    'Do not cite OWASP from memory. Do not provide a final answer until the required tool succeeds.'
                ),
            })
            self.tool_events.append({
                'kind': 'skill_policy',
                'status': 'error',
                'error': policy_error.get('error'),
                'message': policy_error.get('message'),
                'required_tool': policy_error.get('required_tool'),
            })
            self._trace(
                'skill_policy_blocked_final_response',
                error=policy_error.get('error'),
                required_tool=policy_error.get('required_tool'),
                blocked_content_chars=len(content),
            )
        if self.active_skill_name:
            record_skill_event(self.active_skill_name, 'failure')
        self._notify_stream()
        return True

    def call_model(self, run_id: int | None = None):
        if run_id is None:
            run_id = self._start_generation()
        if run_id is None:
            return None

        try:
            selected_skill = self._select_skill_for_current_request()
            if not self._configure_request_skill(run_id, selected_skill):
                return None

            for turn_index in range(0, self.MAX_AUTO_TURNS):
                with self.lock:
                    if not self._is_current_run(run_id):
                        return None
                    self.loop_turn = turn_index

                response = self._call_model_once(run_id)
                if response is None:
                    return None

                content = str(response.get('content') or '').strip()
                tool_calls = response.get('tool_calls') or []

                if tool_calls:
                    for tool_call in tool_calls:
                        if not self._execute_callable(tool_call, run_id):
                            return None
                    continue

                if content == self.DONE:
                    with self.lock:
                        if not self._is_current_run(run_id):
                            return None
                        self.messages.pop()
                        self._trace('done_token_received')
                    return content

                if content == '':
                    with self.lock:
                        if not self._is_current_run(run_id):
                            return None
                        self.messages.pop()
                        self.last_error = 'Model returned an empty response.'
                        self._trace('empty_model_response')
                    if self.active_skill_name:
                        record_skill_event(self.active_skill_name, 'failure')
                    return None

                if self.active_skill_name:
                    policy_error = validate_final_response_against_skill_policy(self, content)
                    if policy_error is not None:
                        if self._handle_skill_policy_blocked_final_response(run_id, content, policy_error):
                            continue
                        return None
                    record_skill_event(self.active_skill_name, 'fulfilled')
                    self.last_fulfilled_skill_name = self.active_skill_name
                else:
                    self.last_fulfilled_skill_name = None
                return content

            with self.lock:
                if not self._is_current_run(run_id):
                    return None
                self.last_error = f'Stopped after {self.MAX_AUTO_TURNS} turns without receiving {self.DONE}.'
                self.messages.append({'role': 'assistant', 'content': self.last_error})
                self._trace('max_auto_turns_reached', max_auto_turns=self.MAX_AUTO_TURNS)
            if self.active_skill_name:
                record_skill_event(self.active_skill_name, 'failure')
            return None
        finally:
            self._finish_generation(run_id)
