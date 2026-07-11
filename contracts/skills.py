from __future__ import annotations

from enum import StrEnum
from typing import Self, cast

from pydantic import Field, model_validator

from contracts.base import ContractModel, ResultStatus
from contracts.types import JsonValue


class ResolvedTaskType(StrEnum):
    GENERIC_SKILL_PROCEDURE = 'generic_skill_procedure'
    OWASP_SECURITY_REVIEW = 'owasp_security_review'
    WHOLE_FILE_CODE_OVERVIEW = 'whole_file_code_overview'
    SPECIFIC_FUNCTION_EXPLANATION = 'specific_function_explanation'


class RecommendedToolCall(ContractModel):
    tool: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    reason: str | None = Field(default=None, min_length=1)


class ForbiddenToolCall(ContractModel):
    tool: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class SkillValidation(ContractModel):
    valid: bool
    score: float | None = None
    reasons: list[str] = Field(default_factory=list)


class SkillCandidate(ContractModel):
    skill_name: str = Field(min_length=1)
    score: float | None = None
    distance: float | None = Field(default=None, ge=0)
    priority: int | None = None
    forced: bool = False


class RejectedSkillCandidate(ContractModel):
    skill_name: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    score: float | None = None
    distance: float | None = Field(default=None, ge=0)


class SkillSelectionResult(ContractModel):
    status: ResultStatus
    skill_name: str | None = None
    selection_reason: str | None = None
    message: str | None = None
    validation: SkillValidation | None = None
    distance: float | None = Field(default=None, ge=0)
    forced: bool = False
    best_candidate: SkillCandidate | None = None
    candidates: list[SkillCandidate] = Field(default_factory=list)
    rejected_candidates: list[RejectedSkillCandidate] = Field(default_factory=list)


class ExecutionGuidance(ContractModel):
    resolved_task_type: ResolvedTaskType
    recommended_tool_calls: list[RecommendedToolCall] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_tool_calls: list[ForbiddenToolCall] = Field(default_factory=list)
    procedure_overrides: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_tool_policy(self) -> Self:
        allowed = set(self.allowed_tools)
        forbidden = {call.tool for call in self.forbidden_tool_calls}

        overlap = allowed & forbidden
        if overlap:
            raise ValueError(f'tools cannot be both allowed and forbidden: {sorted(overlap)}')

        invalid_recommendations = {
            call.tool
            for call in self.recommended_tool_calls
            if call.tool not in allowed
        }
        if invalid_recommendations:
            raise ValueError(f'recommended tools must be allowed: {sorted(invalid_recommendations)}')

        return self


class RequestedSkillResult(ContractModel):
    status: ResultStatus
    skill_name: str | None = None
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    selection: SkillSelectionResult | None = None
    guidance: ExecutionGuidance | None = None

    description: str | None = None
    procedure: str | None = None
    metadata_path: str | None = None
    procedure_path: str | None = None
    tools_required: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    when_to_use: list[str] = Field(default_factory=list)
    when_not_to_use: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    message: str | None = None

    def to_payload(self) -> dict[str, JsonValue]:
        payload = super().to_payload()

        if self.skill_name is None:
            payload['skill_name'] = None

        if self.selection is not None:
            selection = self.selection.to_payload()
            if self.selection.skill_name is None:
                selection['skill_name'] = None
            payload['selection'] = selection

        if self.guidance is not None:
            payload.pop('guidance', None)
            payload.update(self.guidance.to_payload())

        if self.skill_name is None:
            for field_name in (
                'tools_required',
                'preconditions',
                'when_to_use',
                'when_not_to_use',
                'exclusions',
            ):
                if field_name not in self.model_fields_set:
                    payload.pop(field_name, None)

        return cast(dict[str, JsonValue], payload)
