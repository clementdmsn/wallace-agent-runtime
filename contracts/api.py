from __future__ import annotations

from typing import Annotated, Literal, cast

from pydantic import Field

from contracts.base import ContractModel
from contracts.events import PendingApproval, SkillPolicyEvent, SkillSelectionEvent, ToolEvent
from contracts.types import JsonValue


RuntimeEvent = Annotated[
    ToolEvent | SkillSelectionEvent | SkillPolicyEvent,
    Field(discriminator='kind'),
]


class VisibleMessage(ContractModel):
    role: Literal['user', 'assistant']
    content: str


class RuntimeStateResponse(ContractModel):
    messages: list[VisibleMessage] = Field(default_factory=list)
    tool_events: list[RuntimeEvent] = Field(default_factory=list)
    runtime_metrics: dict[str, JsonValue] = Field(default_factory=dict)
    active_skill_name: str | None = None
    active_skill_policy: dict[str, JsonValue] = Field(default_factory=dict)
    is_generating: bool
    last_error: str = ''
    pending_approval: PendingApproval | None = None

    def to_payload(self) -> dict[str, JsonValue]:
        payload = self.model_dump(mode='json')
        payload['tool_events'] = [
            event.to_payload()
            for event in self.tool_events
        ]
        return cast(dict[str, JsonValue], payload)


class ApiOkResponse(ContractModel):
    ok: bool = True


class ApiErrorResponse(ContractModel):
    ok: bool = False
    error: str
