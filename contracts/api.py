from __future__ import annotations

from typing import cast

from pydantic import Field

from contracts.base import ContractModel
from contracts.events import PendingApproval
from contracts.types import JsonValue


class VisibleMessage(ContractModel):
    role: str
    content: str


class RuntimeStateResponse(ContractModel):
    messages: list[VisibleMessage] = Field(default_factory=list)
    tool_events: list[dict[str, JsonValue]] = Field(default_factory=list)
    runtime_metrics: dict[str, JsonValue] = Field(default_factory=dict)
    active_skill_name: str | None = None
    active_skill_policy: dict[str, JsonValue] = Field(default_factory=dict)
    is_generating: bool
    last_error: str = ''
    pending_approval: PendingApproval | None = None

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], self.model_dump(mode='json'))


class ApiOkResponse(ContractModel):
    ok: bool = True


class ApiErrorResponse(ContractModel):
    ok: bool = False
    error: str
