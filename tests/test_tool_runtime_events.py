from __future__ import annotations

from agent.tool_call_parsing import ParsedToolCall
from agent.tool_runtime_events import (
    record_tool_call_finished,
    record_tool_call_pending_approval,
    record_tool_call_stale,
    record_tool_call_started,
    trace_payload_for,
)


class FakeTrace:
    def __init__(self):
        self.events = []

    def payload(self, value):
        return {'payload': value}

    def record(self, event: str, **fields) -> None:
        self.events.append({'event': event, **fields})


class FakeAgent:
    def __init__(self):
        self.run_trace = FakeTrace()


def parsed_tool_call() -> ParsedToolCall:
    return ParsedToolCall(
        call_id='call-1',
        name='read_file',
        raw_args='{"path": "README.md"}',
    )


def test_trace_payload_for_returns_original_value_without_trace():
    agent = FakeAgent()
    agent.run_trace = None

    assert trace_payload_for(agent, {'status': 'ok'}) == {'status': 'ok'}


def test_record_tool_call_started_uses_trace_payloads():
    agent = FakeAgent()
    tool_call = {'id': 'call-1'}

    record_tool_call_started(agent, parsed_tool_call(), tool_call)

    assert agent.run_trace.events == [
        {
            'event': 'tool_call_started',
            'call_id': 'call-1',
            'tool': 'read_file',
            'raw_arguments': {'payload': '{"path": "README.md"}'},
            'tool_call': {'payload': tool_call},
        }
    ]


def test_record_tool_call_stale_records_stale_event():
    agent = FakeAgent()

    record_tool_call_stale(agent, parsed_tool_call())

    assert agent.run_trace.events == [
        {'event': 'tool_call_stale', 'call_id': 'call-1', 'tool': 'read_file'}
    ]


def test_record_tool_call_pending_approval_records_result_payload():
    agent = FakeAgent()

    record_tool_call_pending_approval(
        agent,
        parsed_tool_call(),
        'approval_required',
        12.345,
        {'url': 'https://example.com'},
        {'status': 'approval_required'},
    )

    assert agent.run_trace.events == [
        {
            'event': 'tool_call_pending_approval',
            'call_id': 'call-1',
            'tool': 'read_file',
            'status': 'approval_required',
            'duration_ms': 12.35,
            'args': {'payload': {'url': 'https://example.com'}},
            'result': {'payload': {'status': 'approval_required'}},
        }
    ]


def test_record_tool_call_finished_records_hidden_message_payload():
    agent = FakeAgent()
    hidden_message = {'role': 'tool', 'content': '{"status": "ok"}'}

    record_tool_call_finished(
        agent,
        parsed_tool_call(),
        'ok',
        1.234,
        {'path': 'README.md'},
        {'status': 'ok'},
        hidden_message,
    )

    assert agent.run_trace.events == [
        {
            'event': 'tool_call_finished',
            'call_id': 'call-1',
            'tool': 'read_file',
            'status': 'ok',
            'duration_ms': 1.23,
            'args': {'payload': {'path': 'README.md'}},
            'result': {'payload': {'status': 'ok'}},
            'hidden_message': {'payload': hidden_message},
        }
    ]
