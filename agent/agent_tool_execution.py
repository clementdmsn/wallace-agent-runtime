from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from agent.registered_tool_execution import run_tool
from agent.runtime_state import is_current_run, notify_stream, trace
from agent.tool_call_parsing import ParsedToolCall, parse_tool_call
from agent.tool_result_formatting import (
    ToolExecutionResult,
    hidden_tool_message,
    result_status,
    tool_event,
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


def execute_tool_call(agent: Any, tool_call: dict[str, Any], run_id: int) -> bool:
    started = perf_counter()
    parsed = parse_tool_call(tool_call)
    run_trace = getattr(agent, 'run_trace', None)
    trace_payload = run_trace.payload if run_trace is not None else lambda value: value

    trace(
        agent,
        'tool_call_started',
        call_id=parsed.call_id,
        tool=parsed.name,
        raw_arguments=trace_payload(parsed.raw_args),
        tool_call=trace_payload(tool_call),
    )

    with agent.lock:
        if not is_current_run(agent, run_id):
            trace(agent, 'tool_call_stale', call_id=parsed.call_id, tool=parsed.name)
            return False

    execution = run_tool(agent, parsed.name, parsed.raw_args)
    event = tool_event(parsed, execution)

    with agent.lock:
        if not is_current_run(agent, run_id):
            trace(agent, 'tool_call_stale', call_id=parsed.call_id, tool=parsed.name)
            return False
        duration_ms = (perf_counter() - started) * 1000
        status = result_status(execution.result)
        metrics = getattr(agent, 'metrics', None)
        if metrics is not None:
            metrics.record_tool_call(run_id, parsed.name, status, duration_ms)
        agent.tool_events.append(event)
        if isinstance(execution.result, dict) and execution.result.get('status') == 'approval_required':
            approvals = getattr(agent, 'approvals', None)
            if approvals is not None:
                approvals.set(parsed.name, execution.args, execution.result, parsed.call_id)
            else:
                setter = getattr(agent, 'set_pending_approval', None)
                if callable(setter):
                    setter(parsed.name, execution.args, execution.result, parsed.call_id)
            agent.last_error = 'Waiting for user approval.'
            trace(
                agent,
                'tool_call_pending_approval',
                call_id=parsed.call_id,
                tool=parsed.name,
                status=status,
                duration_ms=round(duration_ms, 2),
                args=trace_payload(execution.args),
                result=trace_payload(execution.result),
            )
            notify_stream(agent)
            return False
        hidden_message = hidden_tool_message(parsed, execution)
        agent.messages.append(hidden_message)
        trace(
            agent,
            'tool_call_finished',
            call_id=parsed.call_id,
            tool=parsed.name,
            status=status,
            duration_ms=round(duration_ms, 2),
            args=trace_payload(execution.args),
            result=trace_payload(execution.result),
            hidden_message=trace_payload(hidden_message),
        )

    notify_stream(agent)
    return True
