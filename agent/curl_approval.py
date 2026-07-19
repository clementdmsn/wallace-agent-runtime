from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from agent.agent_tool_execution import validate_registered_tool_result
from contracts.api import ApiErrorResponse
from tools.curl_tool import add_domain_to_whitelist
from tools.tools import TOOLS

if TYPE_CHECKING:
    from agent.runtime import AgentRuntime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurlApprovalResponse:
    payload: dict[str, Any]
    status_code: int


def model_safe_curl_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and result.get("status") == "approval_required":
        return {
            "status": "error",
            "url": result.get("url"),
            "domain": result.get("domain"),
            "error": "domain is not whitelisted",
        }
    if isinstance(result, dict):
        return result
    return {"status": "error", "error": str(result)}


def resolve_curl_approval(runtime: AgentRuntime, approval_id: str, action: str) -> CurlApprovalResponse:
    if action not in {"approve", "deny"}:
        return CurlApprovalResponse({"ok": False, "error": "Action must be approve or deny"}, 400)

    pending = runtime.agent.approvals.snapshot()
    if pending is not None and approval_id and pending.get("approval_id") != approval_id:
        pending = None
    if pending is None:
        return CurlApprovalResponse({"ok": False, "error": "No matching pending approval"}, 404)

    if action == "approve":
        tool_result_response = approved_tool_result(runtime, pending, approval_id)
        if tool_result_response.status_code != 200 or "pending_approval" in tool_result_response.payload:
            return tool_result_response
        tool_result = tool_result_response.payload
    else:
        tool_result = denied_tool_result(pending)

    started = runtime.resume_with_resolved_tool_result(pending, tool_result, approval_id or None)
    if not started:
        return CurlApprovalResponse({"ok": False, "error": "Generation already in progress"}, 409)

    return CurlApprovalResponse({"ok": True}, 200)


def approved_tool_result(
    runtime: AgentRuntime,
    pending: dict[str, Any],
    approval_id: str,
) -> CurlApprovalResponse:
    result = add_domain_to_whitelist(str(pending.get("domain") or ""))
    if result.get("status") != "ok":
        return CurlApprovalResponse({"ok": False, "error": result.get("error", "Approval failed")}, 500)

    tool = TOOLS.get(str(pending.get("tool") or ""))
    if tool is None:
        return CurlApprovalResponse({"ok": False, "error": "Pending tool is no longer registered"}, 500)

    raw_tool_result = tool.func(**dict(pending.get("args") or {}))
    try:
        raw_tool_result = validate_registered_tool_result(
            str(pending.get("tool") or "curl_url"),
            raw_tool_result,
        )
    except ValidationError:
        logger.exception("curl approval tool result contract validation failed")
        error = ApiErrorResponse(error="Curl approval result failed contract validation.")
        return CurlApprovalResponse(error.to_payload(), 500)

    if isinstance(raw_tool_result, dict) and raw_tool_result.get("status") == "approval_required":
        replaced = runtime.agent.approvals.replace(
            approval_id or None,
            str(pending.get("tool") or "curl_url"),
            dict(pending.get("args") or {}),
            raw_tool_result,
            str(pending.get("call_id") or ""),
        )
        if not replaced:
            return CurlApprovalResponse({"ok": False, "error": "No matching pending approval"}, 404)
        return CurlApprovalResponse({"ok": True, "pending_approval": runtime.agent.approvals.snapshot()}, 200)

    return CurlApprovalResponse(model_safe_curl_result(raw_tool_result), 200)


def denied_tool_result(pending: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "error",
        "url": pending.get("url"),
        "domain": pending.get("domain"),
        "error": "domain is not whitelisted",
        "message": "The user denied adding this domain to the curl whitelist.",
    }
