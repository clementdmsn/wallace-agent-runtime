from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from agent.agent_skill_policy import (
    remember_owasp_reference_search,
    remember_verified_symbols,
    validate_tool_call_against_skill_policy,
)
from skills.skills import record_skill_event
from tools.tools import TOOLS


@dataclass
class ParsedToolCall:
    call_id: str
    name: str
    raw_args: str


@dataclass
class ToolExecutionResult:
    kind: str
    args: dict[str, Any]
    result: object


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


def parse_tool_call(tool_call: dict[str, Any]) -> ParsedToolCall:
    function = tool_call.get('function') or {}
    return ParsedToolCall(
        call_id=str(tool_call.get('id', '')),
        name=str(function.get('name', '')),
        raw_args=function.get('arguments', '{}') or '{}',
    )


def parse_tool_args(raw_args: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        args = json.loads(raw_args)
        if not isinstance(args, dict):
            raise ValueError('call arguments must decode to an object')
    except Exception as exc:
        return None, {'status': 'error', 'error': f'invalid call arguments: {exc}'}
    return args, None


def record_active_skill_event(agent: Any, event: str) -> None:
    if agent.active_skill_name:
        record_skill_event(agent.active_skill_name, event)


def apply_skill_authoring_retry_policy(agent: Any, call_name: str, result: object) -> object:
    if call_name not in {'create_skill', 'finalize_skill_draft', 'repair_skill_draft'} or not isinstance(result, dict):
        return result

    if result.get('status') == 'ok':
        agent.skill_creation_failures = 0
        return result

    if result.get('error') != 'json_payload failed skill quality validation':
        return result

    agent.skill_creation_failures = getattr(agent, 'skill_creation_failures', 0) + 1
    if agent.skill_creation_failures < 3:
        return result

    return {
        **result,
        'retry_limit_reached': True,
        'message': (
            'Skill draft validation failed after 3 attempts. Stop retrying and show the user '
            'the draft paths and validation errors.'
        ),
    }


def execute_registered_tool(agent: Any, call_name: str, args: dict[str, Any]) -> object:
    policy_error = validate_tool_call_against_skill_policy(agent, call_name, args)
    if policy_error is not None:
        record_active_skill_event(agent, 'failure')
        return policy_error

    record_active_skill_event(agent, 'used')
    result = TOOLS[call_name].func(**args)
    result = apply_skill_authoring_retry_policy(agent, call_name, result)
    remember_verified_symbols(agent, call_name, args, result)
    remember_owasp_reference_search(agent, call_name, result)

    if agent.active_skill_name:
        agent.skill_tool_call_index += 1
        if isinstance(result, dict) and result.get('status') == 'ok':
            record_skill_event(agent.active_skill_name, 'success')
        else:
            record_skill_event(agent.active_skill_name, 'failure')

    return result


def run_tool(agent: Any, call_name: str, raw_args: str) -> ToolExecutionResult:
    kind = 'tool'
    args, parse_error = parse_tool_args(raw_args)
    if parse_error is not None:
        return ToolExecutionResult(kind=kind, args={}, result=parse_error)

    assert args is not None
    if call_name not in TOOLS:
        return ToolExecutionResult(
            kind=kind,
            args=args,
            result={
                'status': 'error',
                'error': f'unknown tool: {call_name}',
                'message': 'Only registered tools are executable.',
            },
        )

    try:
        result = execute_registered_tool(agent, call_name, args)
    except Exception as exc:
        record_active_skill_event(agent, 'failure')
        result = {'status': 'error', 'error': str(exc)}

    return ToolExecutionResult(kind=kind, args=args, result=result)


def tool_event(parsed: ParsedToolCall, execution: ToolExecutionResult) -> dict[str, Any]:
    return {
        'id': parsed.call_id,
        'kind': execution.kind,
        execution.kind: parsed.name,
        'args': execution.args,
        'result': execution.result,
    }


def hidden_tool_message(parsed: ParsedToolCall, execution: ToolExecutionResult) -> dict[str, Any]:
    return {
        'role': 'tool',
        'tool_call_id': parsed.call_id or f'{execution.kind}:{parsed.name}',
        'content': json.dumps(
            result_payload(parsed.name, execution.result, execution.kind),
            ensure_ascii=False,
        ),
    }


def append_resolved_tool_result(agent: Any, pending: dict[str, Any], result: dict[str, Any]) -> None:
    parsed = ParsedToolCall(
        call_id=str(pending.get('call_id') or ''),
        name=str(pending.get('tool') or 'curl_url'),
        raw_args=json.dumps(pending.get('args') or {}),
    )
    execution = ToolExecutionResult(
        kind='tool',
        args=dict(pending.get('args') or {}),
        result=result,
    )
    with agent.lock:
        agent.tool_events.append(tool_event(parsed, execution))
        agent.messages.append(hidden_tool_message(parsed, execution))
        if agent.last_error == 'Waiting for user approval.':
            agent.last_error = ''
    agent._notify_stream()


def result_status(result: object) -> str:
    if isinstance(result, dict):
        return str(result.get('status', 'unknown'))
    return 'ok'


def execute_tool_call(agent: Any, tool_call: dict[str, Any], run_id: int) -> bool:
    started = perf_counter()
    parsed = parse_tool_call(tool_call)
    trace = getattr(agent, 'run_trace', None)
    trace_payload = trace.payload if trace is not None else lambda value: value
    trace_record = getattr(agent, '_trace', None)

    if callable(trace_record):
        trace_record(
            'tool_call_started',
            call_id=parsed.call_id,
            tool=parsed.name,
            raw_arguments=trace_payload(parsed.raw_args),
            tool_call=trace_payload(tool_call),
        )

    with agent.lock:
        if not agent._is_current_run(run_id):
            if callable(trace_record):
                trace_record('tool_call_stale', call_id=parsed.call_id, tool=parsed.name)
            return False

    execution = run_tool(agent, parsed.name, parsed.raw_args)
    event = tool_event(parsed, execution)

    with agent.lock:
        if not agent._is_current_run(run_id):
            if callable(trace_record):
                trace_record('tool_call_stale', call_id=parsed.call_id, tool=parsed.name)
            return False
        duration_ms = (perf_counter() - started) * 1000
        status = result_status(execution.result)
        metrics = getattr(agent, 'metrics', None)
        if metrics is not None:
            metrics.record_tool_call(run_id, parsed.name, status, duration_ms)
        agent.tool_events.append(event)
        if isinstance(execution.result, dict) and execution.result.get('status') == 'approval_required':
            setter = getattr(agent, 'set_pending_approval', None)
            if callable(setter):
                setter(parsed.name, execution.args, execution.result, parsed.call_id)
            agent.last_error = 'Waiting for user approval.'
            if callable(trace_record):
                trace_record(
                    'tool_call_pending_approval',
                    call_id=parsed.call_id,
                    tool=parsed.name,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                    args=trace_payload(execution.args),
                    result=trace_payload(execution.result),
                )
            agent._notify_stream()
            return False
        hidden_message = hidden_tool_message(parsed, execution)
        agent.messages.append(hidden_message)
        if callable(trace_record):
            trace_record(
                'tool_call_finished',
                call_id=parsed.call_id,
                tool=parsed.name,
                status=status,
                duration_ms=round(duration_ms, 2),
                args=trace_payload(execution.args),
                result=trace_payload(execution.result),
                hidden_message=trace_payload(hidden_message),
            )

    agent._notify_stream()
    return True
