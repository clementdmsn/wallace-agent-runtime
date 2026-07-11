from __future__ import annotations
import threading
from typing import Any

from agent.agent import Agent
from agent.agent_tool_execution import append_resolved_tool_result


class AgentRuntime:
    def __init__(self, agent: Agent | None = None):
        self.agent = agent or Agent()
        self.worker: threading.Thread | None = None
        self.state_lock = threading.Lock()

    def start_generation(self, submitted: dict[str, Any] | None = None) -> bool:
        with self.state_lock:
            if self.agent.is_busy():
                return False
            if self.worker is not None and self.worker.is_alive():
                return False

            run_id = self.agent.reserve_generation(submitted)
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
            if self.agent.is_busy():
                return False
            if self.worker is not None and self.worker.is_alive():
                return False

            current_pending = self.agent.snapshot_pending_approval()
            if current_pending is None:
                return False
            if approval_id is not None and current_pending.get("approval_id") != approval_id:
                return False

            run_id = self.agent.reserve_generation()
            if run_id is None:
                return False

            cleared = self.agent.clear_pending_approval(approval_id)
            if cleared is None:
                self.agent._finish_generation(run_id)
                return False

            append_resolved_tool_result(self.agent, pending, tool_result)
            self.worker = threading.Thread(target=self.agent.call_model, args=(run_id,), daemon=True)
            self.worker.start()
            return True


