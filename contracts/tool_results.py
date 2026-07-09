from __future__ import annotations

from typing import Any

from pydantic import Field

from contracts.base import ContractModel, ResultStatus


class ToolResult(ContractModel):
    status: ResultStatus
    message: str | None = None
    error: str | None = None


class GenericToolResult(ToolResult):
    path: str | None = None
    root: str | None = None
    name: str | None = None
    command: str | None = None
    returncode: int | None = None
    stdout: str | None = None
    stdout_truncated: bool | None = None
    stderr: str | None = None
    stderr_truncated: bool | None = None
    content: str | None = None
    truncated: bool | None = None
    line_numbered: bool | None = None
    matches: list[str] | None = None
    count: int | None = None
    replacements: int | None = None
    created: bool | None = None
    bytes_written: int | None = None
    result: Any | None = None
    url: str | None = None
    final_url: str | None = None
    title: str | None = None
    approval_id: str | None = None
    domain: str | None = None


class CodeSymbol(ContractModel):
    name: str | None = None
    qualified_name: str | None = None
    kind: str | None = None
    lines: list[int | None]


class CodeSummaryResult(ToolResult):
    path: str
    content: str | None = None


class ListCodeSymbolsResult(ToolResult):
    path: str
    symbols: list[CodeSymbol] = Field(default_factory=list)
    content: list[CodeSymbol] = Field(default_factory=list)


class FunctionExplanationContent(ContractModel):
    qualified_name: str | None = None
    kind: str | None = None
    lines: list[int | None]
    docstring: str | None = None
    params: list[Any] = Field(default_factory=list)
    decorators: list[Any] = Field(default_factory=list)
    calls: list[str] = Field(default_factory=list)
    returns: list[str] = Field(default_factory=list)
    raises: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    reads: list[str] = Field(default_factory=list)
    instance_attributes: list[Any] = Field(default_factory=list)
    nested_symbols: list[str | None] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    summary: str


class ExplainFunctionResult(ToolResult):
    path: str
    symbol: str
    content: FunctionExplanationContent | list[str] | str | None = None
    error_type: str | None = None
    repr: str | None = None


class CurlResult(ToolResult):
    url: str | None = None
    final_url: str | None = None
    domain: str | None = None
    title: str | None = None
    content: str | None = None
    truncated: bool | None = None
    approval_id: str | None = None


class SkillIndexMatch(ContractModel):
    row_id: int
    distance: float
    skill_name: str
    source_path: str
    chunk_index: int
    text: str


class SkillIndexResult(ToolResult):
    path: str | None = None
    index_path: str | None = None
    map_path: str | None = None
    created: bool | None = None
    skipped: bool | None = None
    rows_added: int | None = None
    total_rows: int | None = None
    source_count: int | None = None
    query: str | None = None
    count: int | None = None
    matches: list[SkillIndexMatch] = Field(default_factory=list)
    expected_chunker_version: int | None = None
    actual_chunker_version: int | None = None


class OwaspCorpusError(ContractModel):
    line: int
    error: str


class OwaspReferenceMatch(ContractModel):
    row_id: int
    distance: float
    source: str
    version: str
    reference_id: str
    title: str
    category: str
    url: str
    text: str


class OwaspReferenceResult(ToolResult):
    path: str | None = None
    record_count: int | None = None
    errors: list[OwaspCorpusError] = Field(default_factory=list)
    content_hash: str | None = None
    index_path: str | None = None
    map_path: str | None = None
    total_rows: int | None = None
    query: str | None = None
    count: int | None = None
    matches: list[OwaspReferenceMatch] = Field(default_factory=list)
    expected_chunker_version: int | None = None
    actual_chunker_version: int | None = None


class ReviewTarget(ContractModel):
    path: str
    kind: str
    suffix: str
    size_bytes: int


class ReviewTargetResult(ToolResult):
    root: str | None = None
    targets: list[ReviewTarget] = Field(default_factory=list)
    count: int | None = None
    total_candidates: int | None = None
    truncated: bool | None = None
    max_files: int | None = None
    skipped_directories: list[str] = Field(default_factory=list)


class SkillAuthoringResult(ToolResult):
    skill_name: str | None = None
    skill_id: str | None = None
    description: str | None = None
    procedure: str | None = None
    metadata_path: str | None = None
    procedure_path: str | None = None
    draft_id: str | None = None
    draft_metadata_path: str | None = None
    draft_procedure_path: str | None = None
    draft_markdown: str | None = None
    draft_json_payload: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    missing_fields: list[str] | None = None
    unexpected_fields: list[str] | None = None
    validation_errors: list[dict[str, Any]] | None = None
    repair_instructions: list[str] | None = None
    repair_suggestions: list[dict[str, Any]] | None = None
    retry_policy: dict[str, Any] | str | None = None
    retry_limit_reached: bool | None = None
    index_result: dict[str, Any] | None = None
    registry_reloaded: bool | None = None
    registry_reload_error: str | None = None
    normalizations: list[dict[str, Any]] | None = None
    applied_repairs: list[dict[str, Any]] | None = None
