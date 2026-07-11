from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from contracts.base import ContractModel
from contracts.skills import ResolvedTaskType
from contracts.types import JsonValue


NonEmptyStr = Annotated[str, Field(min_length=1)]


class PolicyExpectation(StrEnum):
    ALLOWED = 'allowed'
    BLOCKED = 'blocked'


class FinalAnswerExpectation(ContractModel):
    content: NonEmptyStr
    expect_blocked: bool


class CandidateMatch(ContractModel):
    skill_name: NonEmptyStr
    distance: float = Field(ge=0, le=1_000_000)


class ExpectedToolStep(ContractModel):
    tool: NonEmptyStr
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    expect: PolicyExpectation = PolicyExpectation.ALLOWED
    verified_symbols: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_tool_specific_fields(self) -> Self:
        if self.verified_symbols and self.tool != 'list_code_symbols':
            raise ValueError('verified_symbols is only valid for list_code_symbols steps')
        return self


class SkillFixture(ContractModel):
    name: NonEmptyStr
    description: NonEmptyStr
    implementation_name: NonEmptyStr | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    procedure: str = ''
    metadata_path: str = ''
    procedure_path: str = ''
    when_to_use: list[str] = Field(default_factory=list)
    when_not_to_use: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    category: NonEmptyStr = 'general'
    tags: list[NonEmptyStr] = Field(default_factory=list)
    supported_actions: list[NonEmptyStr] = Field(default_factory=list)
    supported_domains: list[NonEmptyStr] = Field(default_factory=list)
    supported_filetypes: list[NonEmptyStr] = Field(default_factory=list)
    required_args: list[NonEmptyStr] = Field(default_factory=list)
    tools_required: list[NonEmptyStr] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, ge=0, le=1_000)
    specificity: int = Field(default=0, ge=0, le=1_000)
    default_score: float = Field(default=0.5, ge=0, le=1)


class OfflineEvalScenario(ContractModel):
    name: NonEmptyStr
    prompt: NonEmptyStr
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    expected_skill: NonEmptyStr | None = None
    expected_resolved_task_type: ResolvedTaskType | None = None
    candidate_matches: list[CandidateMatch] = Field(default_factory=list)
    must_recommend_tools: list[NonEmptyStr] = Field(default_factory=list)
    must_allow_tools: list[NonEmptyStr] = Field(default_factory=list)
    skills: list[SkillFixture] = Field(default_factory=list)
    tool_sequence: list[ExpectedToolStep] = Field(default_factory=list)
    final_answer: FinalAnswerExpectation | None = None
    k: int = Field(default=8, ge=1, le=100)
    threshold: float = Field(default=8.0, ge=0, le=100)

    @model_validator(mode='after')
    def validate_references(self) -> Self:
        skill_names = [skill.name for skill in self.skills]
        unique_skill_names = set(skill_names)
        if len(unique_skill_names) != len(skill_names):
            raise ValueError('skill fixture names must be unique within a scenario')

        if self.expected_skill is None:
            ignored_fields = []
            if self.expected_resolved_task_type is not None:
                ignored_fields.append('expected_resolved_task_type')
            if self.must_recommend_tools:
                ignored_fields.append('must_recommend_tools')
            if self.must_allow_tools:
                ignored_fields.append('must_allow_tools')
            if ignored_fields:
                raise ValueError(
                    'skill-policy expectations require expected_skill: '
                    f'{", ".join(ignored_fields)}'
                )
        if self.expected_skill is not None and self.expected_skill not in unique_skill_names:
            raise ValueError(f'expected_skill references unknown skill fixture: {self.expected_skill}')

        unknown_candidates = {
            match.skill_name
            for match in self.candidate_matches
            if match.skill_name not in unique_skill_names
        }
        if unknown_candidates:
            raise ValueError(f'candidate_matches reference unknown skill fixtures: {sorted(unknown_candidates)}')

        return self


class OfflineEvalDocument(ContractModel):
    schema_version: Literal[1]
    scenarios: list[OfflineEvalScenario]

    @model_validator(mode='after')
    def validate_unique_scenario_names(self) -> Self:
        names = [scenario.name for scenario in self.scenarios]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f'scenario names must be unique: {duplicates}')
        return self
