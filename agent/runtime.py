from __future__ import annotations

import threading
from typing import Any

from agent.agent import Agent
from agent.agent_tool_execution import append_resolved_tool_result
from contracts.api import RuntimeStateResponse


def visible_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", "assistant"))
        if role not in {"user", "assistant"}:
            continue

        content = message.get("content") or ""
        if role == "assistant" and not content and message.get("tool_calls"):
            continue

        visible.append({"role": role, "content": str(content)})

    return visible


def serialize_tool_events(tool_events: list[Any]) -> list[Any]:
    serialized: list[Any] = []
    for event in tool_events:
        if isinstance(event, (dict, list, str, int, float, bool)) or event is None:
            serialized.append(event)
        else:
            try:
                serialized.append(event.__dict__)
            except AttributeError:
                serialized.append(str(event))
    return serialized


class AgentRuntime:
    def __init__(self, agent: Agent | None = None):
        self.agent = agent or Agent()
        self.worker: threading.Thread | None = None
        self.state_lock = threading.Lock()

    def snapshot_state(self) -> RuntimeStateResponse:
        with self.agent.lock:
            messages = [dict(message) for message in self.agent.messages]
            tool_events = [dict(event) for event in self.agent.tool_events]
            runtime_metrics = self.agent.metrics.snapshot()
            last_error = self.agent.last_error
            is_generating = self.agent.is_generating
            pending_approval = self.agent.approvals.snapshot()
            active_skill_name = self.agent.active_skill_name
            active_skill_policy = dict(self.agent.active_skill_policy or {})

        return RuntimeStateResponse(
            messages=visible_messages(messages),
            tool_events=serialize_tool_events(tool_events),
            runtime_metrics=runtime_metrics,
            active_skill_name=active_skill_name,
            active_skill_policy=active_skill_policy,
            is_generating=is_generating,
            last_error=last_error,
            pending_approval=pending_approval,
        )

    def start_generation(self, submitted: dict[str, Any] | None = None) -> bool:
        with self.state_lock:
            if self.agent.generation.is_busy():
                return False
            if self.worker is not None and self.worker.is_alive():
                return False

            run_id = self.agent.generation.reserve(submitted)
            if run_id is None:
                return False

            self.worker = threading.Thread(target=self.agent.call_model, args=(run_id,), daemon=True)
            self.worker.start()
            return True

    def resume_with_resolved_tool_result(
        self,
        pending: dict[str, Any],
        tool_result: dict[str, Any],
        approval_id: str | None,
    ) -> bool:
        with self.state_lock:
            if self.agent.generation.is_busy():
                return False
            if self.worker is not None and self.worker.is_alive():
                return False

            current_pending = self.agent.approvals.snapshot()
            if current_pending is None:
                return False
            if approval_id is not None and current_pending.get("approval_id") != approval_id:
                return False

            run_id = self.agent.generation.reserve()
            if run_id is None:
                return False

            cleared = self.agent.approvals.clear(approval_id)
            if cleared is None:
                self.agent.generation.finish(run_id)
                return False

            append_resolved_tool_result(self.agent, pending, tool_result)
            self.worker = threading.Thread(target=self.agent.call_model, args=(run_id,), daemon=True)
            self.worker.start()
            return True
