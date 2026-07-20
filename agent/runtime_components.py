from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent.pending_approval import (
    build_pending_approval_payload,
    clear_pending_approval,
    replace_pending_approval,
    set_pending_approval,
    snapshot_pending_approval,
)
from agent.runtime_state import finish_generation, is_busy, reserve_generation

if TYPE_CHECKING:
    from agent.agent import Agent


class ApprovalRuntime:
    def __init__(self, agent: Agent):
        self.agent = agent

    def snapshot(self) -> dict[str, Any] | None:
        return snapshot_pending_approval(self.agent)

    def build_payload(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> dict[str, Any]:
        return build_pending_approval_payload(tool_name, args, result, call_id)

    def set(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> None:
        set_pending_approval(self.agent, tool_name, args, result, call_id)

    def replace(
        self,
        previous_approval_id: str | None,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        call_id: str = '',
    ) -> bool:
        return replace_pending_approval(
            self.agent,
            previous_approval_id,
            tool_name,
            args,
            result,
            call_id,
        )

    def clear(self, approval_id: str | None = None) -> dict[str, Any] | None:
        return clear_pending_approval(self.agent, approval_id)


class GenerationRuntime:
    def __init__(self, agent: Agent):
        self.agent = agent

    def is_busy(self) -> bool:
        return is_busy(self.agent)

    def reserve(self, submitted: dict[str, Any] | None = None) -> int | None:
        return reserve_generation(self.agent, submitted)

    def finish(self, run_id: int) -> None:
        finish_generation(self.agent, run_id)

