from __future__ import annotations

from typing import Any

from pydantic import Field

from contracts.base import ContractModel
from contracts.events import PendingApproval


class VisibleMessage(ContractModel):
    role: str
    content: str


class RuntimeStateResponse(ContractModel):
    messages: list[VisibleMessage] = Field(default_factory=list)
    tool_events: list[dict[str, Any]] = Field(default_factory=list)
    runtime_metrics: dict[str, Any] = Field(default_factory=dict)
    active_skill_name: str | None = None
    active_skill_policy: dict[str, Any] = Field(default_factory=dict)
    is_generating: bool
    last_error: str = ''
    pending_approval: PendingApproval | None = None


class ApiOkResponse(ContractModel):
    ok: bool = True


class ApiErrorResponse(ContractModel):
    ok: bool = False
    error: str
