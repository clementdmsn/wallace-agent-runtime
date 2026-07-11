from __future__ import annotations

from openai import OpenAI
import logging
import os
import threading
from typing import Any

from system_prompt.system_prompt import build_system_prompt
from agent.agent_metrics import AgentMetrics
from agent.agent_skill_policy import (
    reset_skill_state,
    set_skill_state_from_selection,
    validate_final_response_against_skill_policy,
)
from agent.agent_tool_execution import execute_tool_call
from agent.model_lifecycle import (
    append_assistant_placeholder,
    call_model_once,
    fail_model_call,
    finish_model_call,
    normalize_message_for_api,
    prepare_model_call,
)
from agent.pending_approval import (
    build_pending_approval_payload,
    clear_pending_approval,
    replace_pending_approval,
    set_pending_approval,
    snapshot_pending_approval,
)
from agent.run_trace import RunTrace
from agent.runtime_state import (
    append_message_locked,
    finish_generation,
    is_busy,
    notify_stream,
    reserve_generation,
    snapshot_messages,
    snapshot_runtime_metrics,
    snapshot_tool_events,
    trace,
)
from agent.skill_selection import (
    append_skill_policy_event,
    append_skill_selection_event,
    configure_request_skill,
    latest_user_text,
    select_skill_for_current_request,
    skill_selection_event_status as normalize_skill_selection_event_status,
    skill_selection_text_for_latest_user,
)
from contracts.events import SkillPolicyEvent, SkillSelectionEvent, SkillSelectionEventStatus
from config import SETTINGS
from skills.skills import record_skill_event, request_skill_for_intent

logger = logging.getLogger(__name__)


def skill_selection_event_status(value: object) -> SkillSelectionEventStatus:
    return normalize_skill_selection_event_status(value)


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

    def _request_skill_for_intent(self, selection_text: str) -> dict[str, Any]:
        return request_skill_for_intent(selection_text)

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
        append_message_locked(self, submitted)

    def snapshot_messages(self) -> list[dict[str, Any]]:
        return snapshot_messages(self)

    def snapshot_tool_events(self) -> list[dict[str, Any]]:
        return snapshot_tool_events(self)

    def snapshot_runtime_metrics(self) -> dict[str, object]:
        return snapshot_runtime_metrics(self)

    def snapshot_pending_approval(self) -> dict[str, Any] | None:
        return snapshot_pending_approval(self)

    def _build_pending_approval_payload(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> dict[str, Any]:
        return build_pending_approval_payload(tool_name, args, result, call_id)

    def set_pending_approval(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> None:
        set_pending_approval(self, tool_name, args, result, call_id)

    def replace_pending_approval(
        self,
        previous_approval_id: str | None,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> bool:
        return replace_pending_approval(self, previous_approval_id, tool_name, args, result, call_id)

    def clear_pending_approval(self, approval_id: str | None = None) -> dict[str, Any] | None:
        return clear_pending_approval(self, approval_id)

    def is_busy(self) -> bool:
        return is_busy(self)

    def _notify_stream(self):
        notify_stream(self)

    def _trace(self, event: str, **fields: Any) -> None:
        trace(self, event, **fields)

    def reserve_generation(self, submitted: dict[str, Any] | None = None) -> int | None:
        return reserve_generation(self, submitted)

    def _start_generation(self) -> int | None:
        return self.reserve_generation()

    def _finish_generation(self, run_id: int):
        finish_generation(self, run_id)

    def _normalize_message_for_api(self, message: dict[str, Any]) -> dict[str, Any]:
        return normalize_message_for_api(message)

    def _latest_user_text(self) -> str:
        return latest_user_text(self)

    def _skill_selection_text_for_latest_user(self) -> str:
        return skill_selection_text_for_latest_user(self)

    def _prepare_model_call(self, run_id: int) -> tuple[list[dict[str, Any]], int, int | None] | None:
        return prepare_model_call(self, run_id)

    def _append_assistant_placeholder(self, run_id: int) -> dict[str, Any] | None:
        return append_assistant_placeholder(self, run_id)

    def _finish_model_call(
        self,
        run_id: int,
        model_call_index: int | None,
        turn_index: int,
        assistant_message: dict[str, Any],
    ) -> dict[str, Any] | None:
        return finish_model_call(self, run_id, model_call_index, turn_index, assistant_message)

    def _fail_model_call(
        self,
        run_id: int,
        model_call_index: int | None,
        turn_index: int,
        assistant_message: dict[str, Any],
        exc: Exception,
    ) -> dict[str, Any] | None:
        return fail_model_call(self, run_id, model_call_index, turn_index, assistant_message, exc)

    def _select_skill_for_current_request(self) -> dict[str, Any] | None:
        return select_skill_for_current_request(self)

    def _append_skill_selection_event(self, event: SkillSelectionEvent) -> None:
        append_skill_selection_event(self, event)

    def _append_skill_policy_event(self, event: SkillPolicyEvent) -> None:
        append_skill_policy_event(self, event)

    def _configure_request_skill(
        self,
        run_id: int,
        selected_skill: dict[str, Any] | None,
    ) -> bool:
        return configure_request_skill(self, run_id, selected_skill)

    def _call_model_once(self, run_id: int) -> dict[str, Any] | None:
        return call_model_once(self, run_id)

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
            self._append_skill_policy_event(
                SkillPolicyEvent(
                    kind='skill_policy',
                    status='error',
                    error=policy_error.get('error'),
                    message=policy_error.get('message'),
                    required_tool=policy_error.get('required_tool'),
                )
            )
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
