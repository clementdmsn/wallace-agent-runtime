from __future__ import annotations

from openai import OpenAI
import os
import threading
from typing import Any

from system_prompt.system_prompt import build_system_prompt
from agent.agent_metrics import AgentMetrics
from agent.agent_skill_policy import (
    reset_skill_state,
    set_skill_state_from_selection,
)
from agent.agent_tool_execution import execute_tool_call
from agent.final_response_policy import handle_skill_policy_blocked_final_response
from agent.run_trace import RunTrace
from agent.runtime_components import AgentRunner, ApprovalRuntime, GenerationRuntime
from agent.runtime_state import (
    append_message_locked,
    notify_stream,
    snapshot_messages,
    snapshot_runtime_metrics,
    snapshot_tool_events,
    trace,
)
from config import SETTINGS
from skills.skills import record_skill_event, request_skill_for_intent

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
        self.approvals = ApprovalRuntime(self)
        self.generation = GenerationRuntime(self)
        self.runner = AgentRunner(self)

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

    def _record_skill_event(self, skill_name: str, event: str) -> None:
        record_skill_event(skill_name, event)

    def _start_run_trace(self, run_id: int) -> RunTrace:
        return RunTrace.start(run_id)

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
        return self.approvals.snapshot()

    def _build_pending_approval_payload(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> dict[str, Any]:
        return self.approvals.build_payload(tool_name, args, result, call_id)

    def set_pending_approval(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> None:
        self.approvals.set(tool_name, args, result, call_id)

    def replace_pending_approval(
        self,
        previous_approval_id: str | None,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> bool:
        return self.approvals.replace(previous_approval_id, tool_name, args, result, call_id)

    def clear_pending_approval(self, approval_id: str | None = None) -> dict[str, Any] | None:
        return self.approvals.clear(approval_id)

    def is_busy(self) -> bool:
        return self.generation.is_busy()

    def _notify_stream(self):
        notify_stream(self)

    def _trace(self, event: str, **fields: Any) -> None:
        trace(self, event, **fields)

    def reserve_generation(self, submitted: dict[str, Any] | None = None) -> int | None:
        return self.generation.reserve(submitted)

    def _start_generation(self) -> int | None:
        return self.reserve_generation()

    def _finish_generation(self, run_id: int):
        self.generation.finish(run_id)

    def _execute_callable(self, tool_call: dict[str, Any], run_id: int) -> bool:
        return execute_tool_call(self, tool_call, run_id)

    def _handle_skill_policy_blocked_final_response(
        self,
        run_id: int,
        content: str,
        policy_error: dict[str, Any],
    ) -> bool:
        return handle_skill_policy_blocked_final_response(self, run_id, content, policy_error)

    def call_model(self, run_id: int | None = None):
        return self.runner.call_model(run_id)
