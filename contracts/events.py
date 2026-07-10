from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from contracts.base import ContractModel, ResultStatus


class ToolEvent(ContractModel):
    id: str = ''
    kind: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: Any | None = None
    tool: str | None = None
    status: str | None = None
    error: str | None = None
    message: str | None = None
    skill_name: str | None = None


class SkillSelectionEvent(ContractModel):
    kind: Literal['skill_selection']
    status: ResultStatus | str
    skill_name: str | None = None
    selection: dict[str, Any] | None = None
    error: str | None = None


class SkillPolicyEvent(ContractModel):
    kind: Literal['skill_policy']
    status: ResultStatus | str
    error: str | None = None
    message: str | None = None
    required_tool: str | None = None


class PendingApproval(ContractModel):
    tool: str
    call_id: str = ''
    args: dict[str, Any] = Field(default_factory=dict)
    approval_id: str
    domain: str
    url: str | None = None
