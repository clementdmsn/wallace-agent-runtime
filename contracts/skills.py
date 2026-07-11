from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from contracts.base import ContractModel
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
