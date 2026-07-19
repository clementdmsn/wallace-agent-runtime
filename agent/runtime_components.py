from __future__ import annotations

from typing import Any

from agent import pending_approval, run_loop, runtime_state


class ApprovalRuntime:
    def __init__(self, agent: Any):
        self.agent = agent

    def snapshot(self) -> dict[str, Any] | None:
        return pending_approval.snapshot_pending_approval(self.agent)

    def build_payload(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> dict[str, Any]:
        return pending_approval.build_pending_approval_payload(tool_name, args, result, call_id)

    def set(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> None:
        pending_approval.set_pending_approval(self.agent, tool_name, args, result, call_id)

    def replace(
        self,
        previous_approval_id: str | None,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> bool:
        return pending_approval.replace_pending_approval(
            self.agent,
            previous_approval_id,
            tool_name,
            args,
            result,
            call_id,
        )

    def clear(self, approval_id: str | None = None) -> dict[str, Any] | None:
        return pending_approval.clear_pending_approval(self.agent, approval_id)


class GenerationRuntime:
    def __init__(self, agent: Any):
        self.agent = agent

    def is_busy(self) -> bool:
        return runtime_state.is_busy(self.agent)

    def reserve(self, submitted: dict[str, Any] | None = None) -> int | None:
        return runtime_state.reserve_generation(self.agent, submitted)

    def finish(self, run_id: int) -> None:
        runtime_state.finish_generation(self.agent, run_id)


class AgentRunner:
    def __init__(self, agent: Any):
        self.agent = agent

    def call_model(self, run_id: int | None = None) -> str | None:
        return run_loop.call_model(self.agent, run_id)
