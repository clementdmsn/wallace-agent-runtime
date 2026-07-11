from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from contracts.base import ContractModel
from contracts.types import JsonValue


class ToolEventKind(StrEnum):
    TOOL = 'tool'


class ToolEventStatus(StrEnum):
    OK = 'ok'
    ERROR = 'error'
    APPROVAL_REQUIRED = 'approval_required'


class SkillSelectionEventStatus(StrEnum):
    OK = 'ok'
    ERROR = 'error'
    UNKNOWN = 'unknown'


class SkillPolicyEventStatus(StrEnum):
    ERROR = 'error'


class ToolEvent(ContractModel):
    id: str = ''
    kind: Literal[ToolEventKind.TOOL]
    args: dict[str, JsonValue] = Field(default_factory=dict)
    result: JsonValue = None
    tool: str | None = None
    status: ToolEventStatus | None = None
    error: str | None = None
    message: str | None = None
    skill_name: str | None = None


class SkillSelectionEvent(ContractModel):
    kind: Literal['skill_selection']
    status: SkillSelectionEventStatus
    skill_name: str | None = None
    selection: dict[str, JsonValue] | None = None
    error: str | None = None


class SkillPolicyEvent(ContractModel):
    kind: Literal['skill_policy']
    status: SkillPolicyEventStatus
    error: str | None = None
    message: str | None = None
    required_tool: str | None = None


class PendingApproval(ContractModel):
    tool: str
    call_id: str = ''
    args: dict[str, JsonValue] = Field(default_factory=dict)
    approval_id: str
    domain: str
    url: str | None = None
