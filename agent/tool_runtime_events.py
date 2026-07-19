from __future__ import annotations

from typing import Any

from agent.runtime_state import trace
from agent.tool_call_parsing import ParsedToolCall


def trace_payload_for(agent: Any, value: Any) -> Any:
    run_trace = getattr(agent, 'run_trace', None)
    if run_trace is None:
        return value
    return run_trace.payload(value)


def record_tool_call_started(agent: Any, parsed: ParsedToolCall, tool_call: dict[str, Any]) -> None:
    trace(
        agent,
        'tool_call_started',
        call_id=parsed.call_id,
        tool=parsed.name,
        raw_arguments=trace_payload_for(agent, parsed.raw_args),
        tool_call=trace_payload_for(agent, tool_call),
    )


def record_tool_call_stale(agent: Any, parsed: ParsedToolCall) -> None:
    trace(agent, 'tool_call_stale', call_id=parsed.call_id, tool=parsed.name)


def record_tool_call_pending_approval(
    agent: Any,
    parsed: ParsedToolCall,
    status: str,
    duration_ms: float,
    args: dict[str, Any],
    result: object,
) -> None:
    trace(
        agent,
        'tool_call_pending_approval',
        call_id=parsed.call_id,
        tool=parsed.name,
        status=status,
        duration_ms=round(duration_ms, 2),
        args=trace_payload_for(agent, args),
        result=trace_payload_for(agent, result),
    )


def record_tool_call_finished(
    agent: Any,
    parsed: ParsedToolCall,
    status: str,
    duration_ms: float,
    args: dict[str, Any],
    result: object,
    hidden_message: dict[str, Any],
) -> None:
    trace(
        agent,
        'tool_call_finished',
        call_id=parsed.call_id,
        tool=parsed.name,
        status=status,
        duration_ms=round(duration_ms, 2),
        args=trace_payload_for(agent, args),
        result=trace_payload_for(agent, result),
        hidden_message=trace_payload_for(agent, hidden_message),
    )
