from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from agent.registered_tool_execution import run_tool
from agent.runtime_state import is_current_run, notify_stream
from agent.tool_call_parsing import ParsedToolCall, parse_tool_call
from agent.tool_result_formatting import (
    ToolExecutionResult,
    hidden_tool_message,
    result_status,
    tool_event,
)
from agent.tool_runtime_events import (
    record_tool_call_finished,
    record_tool_call_pending_approval,
    record_tool_call_stale,
    record_tool_call_started,
)


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
    notify_stream(agent)


def record_tool_metric(agent: Any, run_id: int, tool_name: str, status: str, duration_ms: float) -> None:
    metrics = getattr(agent, 'metrics', None)
    if metrics is not None:
        metrics.record_tool_call(run_id, tool_name, status, duration_ms)


def is_approval_required(result: object) -> bool:
    return isinstance(result, dict) and result.get('status') == 'approval_required'


def store_pending_approval(agent: Any, parsed: ParsedToolCall, execution: ToolExecutionResult) -> None:
    agent.approvals.set(parsed.name, execution.args, execution.result, parsed.call_id)
    agent.last_error = 'Waiting for user approval.'


def finish_tool_execution(
    agent: Any,
    run_id: int,
    parsed: ParsedToolCall,
    execution: ToolExecutionResult,
    started: float,
) -> bool:
    event = tool_event(parsed, execution)

    with agent.lock:
        if not is_current_run(agent, run_id):
            record_tool_call_stale(agent, parsed)
            return False

        duration_ms = (perf_counter() - started) * 1000
        status = result_status(execution.result)
        record_tool_metric(agent, run_id, parsed.name, status, duration_ms)
        agent.tool_events.append(event)

        if is_approval_required(execution.result):
            store_pending_approval(agent, parsed, execution)
            record_tool_call_pending_approval(
                agent,
                parsed,
                status,
                duration_ms,
                execution.args,
                execution.result,
            )
            notify_stream(agent)
            return False

        hidden_message = hidden_tool_message(parsed, execution)
        agent.messages.append(hidden_message)
        record_tool_call_finished(
            agent,
            parsed,
            status,
            duration_ms,
            execution.args,
            execution.result,
            hidden_message,
        )

    notify_stream(agent)
    return True


def execute_tool_call(agent: Any, tool_call: dict[str, Any], run_id: int) -> bool:
    started = perf_counter()
    parsed = parse_tool_call(tool_call)
    record_tool_call_started(agent, parsed, tool_call)

    with agent.lock:
        if not is_current_run(agent, run_id):
            record_tool_call_stale(agent, parsed)
            return False

    execution = run_tool(agent, parsed.name, parsed.raw_args)
    return finish_tool_execution(agent, run_id, parsed, execution, started)
