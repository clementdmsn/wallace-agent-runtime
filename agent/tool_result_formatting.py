from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agent.tool_call_parsing import ParsedToolCall
from contracts.events import ToolEvent


@dataclass
class ToolExecutionResult:
    kind: str
    args: dict[str, Any]
    result: object


def hidden_tool_message(parsed: ParsedToolCall, execution: ToolExecutionResult) -> dict[str, Any]:
    return {
        'role': 'tool',
        'tool_call_id': parsed.call_id or f'{execution.kind}:{parsed.name}',
        'content': json.dumps(
            result_payload(parsed.name, execution.result, execution.kind),
            ensure_ascii=False,
        ),
    }


def result_payload(name: str, result: object, kind: str) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {kind: name, 'status': 'ok', 'text': str(result)}

    payload = {
        kind: name,
        'status': result.get('status', 'unknown'),
    }
    for key in (
        'path',
        'returncode',
        'stdout',
        'stdout_truncated',
        'stderr',
        'stderr_truncated',
        'content',
        'truncated',
        'message',
        'error',
        'name',
        'root',
        'matches',
        'count',
        'replacements',
        'created',
        'bytes_written',
        'command',
        'result',
        'expected_arguments',
        'provided_arguments',
        'skill_name',
        'description',
        'procedure',
        'metadata_path',
        'procedure_path',
        'tools_required',
        'preconditions',
        'when_to_use',
        'when_not_to_use',
        'exclusions',
        'arguments',
        'execution_notes',
        'selection',
        'candidates',
        'validation',
        'validation_errors',
        'repair_instructions',
        'repair_suggestions',
        'retry_policy',
        'retry_limit_reached',
        'draft_id',
        'draft_metadata_path',
        'draft_procedure_path',
        'draft_markdown',
        'draft_json_payload',
        'resolved_task_type',
        'recommended_tool_calls',
        'allowed_tools',
        'forbidden_tool_calls',
        'procedure_overrides',
        'expected_tool',
        'provided_tool',
        'symbols',
        'verified_symbols',
        'url',
        'final_url',
        'title',
        'approval_id',
        'domain',
    ):
        if key in result:
            payload[key] = result[key]
    return payload


def tool_event(parsed: ParsedToolCall, execution: ToolExecutionResult) -> dict[str, Any]:
    return ToolEvent(
        id=parsed.call_id,
        kind=execution.kind,
        tool=parsed.name if execution.kind == 'tool' else None,
        args=execution.args,
        result=execution.result,
    ).to_payload()


def result_status(result: object) -> str:
    if isinstance(result, dict):
        return str(result.get('status', 'unknown'))
    return 'ok'
