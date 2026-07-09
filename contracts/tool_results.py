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
