from __future__ import annotations

from openai import OpenAI
import os
import threading
from typing import Any

from system_prompt.system_prompt import build_system_prompt
from agent.metrics import AgentMetrics
from agent.run_trace import RunTrace
from agent.runtime_components import ApprovalRuntime, GenerationRuntime
from agent.runtime_state import (
    notify_stream,
    reset_request_skill_state,
)
from agent.run_loop import call_model as run_loop_call_model
from config import SETTINGS


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

    def _initial_messages(self):
        return [{'role': 'system', 'content': build_system_prompt()}]

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
            reset_request_skill_state(self)
            self.metrics.reset_current()

        notify_stream(self)
        return True

    def call_model(self, run_id: int | None = None):
        return run_loop_call_model(self, run_id)
