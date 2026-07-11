from __future__ import annotations

from typing import Any

from contracts.events import PendingApproval


def snapshot_pending_approval(agent: Any) -> dict[str, Any] | None:
    with agent.lock:
        if not agent.pending_approval:
            return None
        return PendingApproval.model_validate(agent.pending_approval).to_payload()


def build_pending_approval_payload(
    tool_name: str,
    args: dict[str, Any],
    result: dict[str, Any],
    call_id: str = '',
) -> dict[str, Any]:
    return PendingApproval(
        tool=tool_name,
        call_id=call_id,
        args=dict(args),
        approval_id=result.get('approval_id'),
        domain=result.get('domain'),
        url=result.get('url') or args.get('url'),
    ).to_payload()


def set_pending_approval(
    agent: Any,
    tool_name: str,
    args: dict[str, Any],
    result: dict[str, Any],
    call_id: str = '',
) -> None:
    with agent.lock:
        agent.pending_approval = build_pending_approval_payload(tool_name, args, result, call_id)


def replace_pending_approval(
    agent: Any,
    previous_approval_id: str | None,
    tool_name: str,
    args: dict[str, Any],
    result: dict[str, Any],
    call_id: str = '',
) -> bool:
    with agent.lock:
        if not agent.pending_approval:
            return False
        if previous_approval_id is not None and agent.pending_approval.get('approval_id') != previous_approval_id:
            return False
        agent.pending_approval = build_pending_approval_payload(tool_name, args, result, call_id)
        agent.last_error = 'Waiting for user approval.'
        return True


def clear_pending_approval(agent: Any, approval_id: str | None = None) -> dict[str, Any] | None:
    with agent.lock:
        if not agent.pending_approval:
            return None
        if approval_id is not None and agent.pending_approval.get('approval_id') != approval_id:
            return None
        pending = PendingApproval.model_validate(agent.pending_approval).to_payload()
        agent.pending_approval = None
        if agent.last_error == 'Waiting for user approval.':
            agent.last_error = ''
        return pending
