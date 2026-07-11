from __future__ import annotations

import json
import math

import pytest
from pydantic import ValidationError

from contracts.traces import RunTraceEvent
from scripts.summarize_run_trace import summarize


def test_run_trace_event_serializes_flattened_payload():
    event = RunTraceEvent(
        ts='2026-07-11T10:00:00+0000',
        event='tool_call_finished',
        run_id=42,
        trace_id='trace-42',
        fields={
            'tool': 'read_file',
            'status': 'ok',
        },
    )

    assert event.to_payload() == {
        'ts': '2026-07-11T10:00:00+0000',
        'event': 'tool_call_finished',
        'run_id': 42,
        'trace_id': 'trace-42',
        'tool': 'read_file',
        'status': 'ok',
    }


@pytest.mark.parametrize('reserved_key', ['ts', 'event', 'run_id', 'trace_id'])
def test_run_trace_event_rejects_reserved_field_collisions(reserved_key: str):
    event = RunTraceEvent(
        ts='2026-07-11T10:00:00+0000',
        event='run_started',
        run_id=1,
        trace_id='trace-1',
        fields={reserved_key: 'collision'},
    )

    with pytest.raises(ValueError, match='trace fields contain reserved keys'):
        event.to_payload()


def test_run_trace_event_rejects_invalid_run_id():
    with pytest.raises(ValidationError):
        RunTraceEvent(
            ts='2026-07-11T10:00:00+0000',
            event='run_started',
            run_id=-1,
            trace_id='trace-1',
        )


@pytest.mark.parametrize(
    ('field_name', 'value'),
    [
        ('event', ''),
        ('trace_id', ''),
    ],
)
def test_run_trace_event_rejects_empty_required_fields(field_name: str, value: str):
    payload = {
        'ts': '2026-07-11T10:00:00+0000',
        'event': 'run_started',
        'run_id': 1,
        'trace_id': 'trace-1',
    }
    payload[field_name] = value

    with pytest.raises(ValidationError):
        RunTraceEvent(**payload)


def test_run_trace_event_allows_json_compatible_nested_fields():
    event = RunTraceEvent(
        ts='2026-07-11T10:00:00+0000',
        event='model_call_finished',
        run_id=2,
        trace_id='trace-2',
        fields={
            'assistant_message': {
                'role': 'assistant',
                'content': 'Hello',
                'metadata': {'tokens': 12, 'streamed': True, 'warnings': None},
            },
            'latencies_ms': [1, 2.5, 3],
        },
    )

    assert event.to_payload()['assistant_message'] == {
        'role': 'assistant',
        'content': 'Hello',
        'metadata': {'tokens': 12, 'streamed': True, 'warnings': None},
    }


def test_run_trace_event_rejects_non_json_fields():
    with pytest.raises(ValidationError):
        RunTraceEvent(
            ts='2026-07-11T10:00:00+0000',
            event='model_call_finished',
            run_id=2,
            trace_id='trace-2',
            fields={'bad': object()},
        )


def test_run_trace_event_rejects_non_finite_json_fields():
    with pytest.raises(ValidationError):
        RunTraceEvent(
            ts='2026-07-11T10:00:00+0000',
            event='model_call_finished',
            run_id=2,
            trace_id='trace-2',
            fields={'metrics': {'latency_ms': math.nan}},
        )


def test_run_trace_event_payload_is_compatible_with_trace_summarizer(tmp_path):
    path = tmp_path / 'run.jsonl'
    events = [
        RunTraceEvent(
            ts='2026-07-11T10:00:00+0000',
            event='trace_started',
            run_id=1,
            trace_id='trace-1',
        ),
        RunTraceEvent(
            ts='2026-07-11T10:00:01+0000',
            event='run_started',
            run_id=1,
            trace_id='trace-1',
            fields={'user_message': 'hey'},
        ),
        RunTraceEvent(
            ts='2026-07-11T10:00:02+0000',
            event='skill_selection_finished',
            run_id=1,
            trace_id='trace-1',
            fields={'skill_name': None},
        ),
        RunTraceEvent(
            ts='2026-07-11T10:00:03+0000',
            event='model_call_finished',
            run_id=1,
            trace_id='trace-1',
            fields={'assistant_message': {'role': 'assistant', 'content': 'Hello'}},
        ),
        RunTraceEvent(
            ts='2026-07-11T10:00:04+0000',
            event='run_finished',
            run_id=1,
            trace_id='trace-1',
            fields={'metrics': {'request_total_ms': 10, 'model_calls': [{'ttft_ms': 4}]}},
        ),
    ]
    lines = [json.dumps(event.to_payload(), sort_keys=True) for event in events]
    path.write_text('\n'.join(lines), encoding='utf-8')

    output = summarize(path)

    assert 'Trace ID: trace-1' in output
    assert 'Status: complete' in output
    assert 'User: hey' in output
    assert 'Skill: none' in output
    assert 'Assistant: Hello' in output
    assert 'Request total ms: 10' in output
    assert 'First token ms: 4' in output
