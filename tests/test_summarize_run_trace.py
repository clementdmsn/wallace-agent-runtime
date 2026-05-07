from __future__ import annotations

import json

from scripts.summarize_run_trace import summarize


def test_summarize_run_trace_reports_core_outcome(tmp_path):
    path = tmp_path / 'run.jsonl'
    events = [
        {'event': 'trace_started', 'trace_id': 'trace-1', 'run_id': 1},
        {'event': 'run_started', 'trace_id': 'trace-1', 'run_id': 1, 'user_message': 'hey'},
        {
            'event': 'skill_selection_finished',
            'trace_id': 'trace-1',
            'run_id': 1,
            'skill_name': None,
        },
        {
            'event': 'model_call_finished',
            'trace_id': 'trace-1',
            'run_id': 1,
            'assistant_message': {'role': 'assistant', 'content': 'Hello'},
        },
        {
            'event': 'run_finished',
            'trace_id': 'trace-1',
            'run_id': 1,
            'metrics': {'request_total_ms': 10, 'model_calls': [{'ttft_ms': 4}]},
        },
    ]
    path.write_text('\n'.join(json.dumps(event) for event in events), encoding='utf-8')

    output = summarize(path)

    assert 'Trace ID: trace-1' in output
    assert 'Status: complete' in output
    assert 'User: hey' in output
    assert 'Skill: none' in output
    assert 'Assistant: Hello' in output
    assert 'Request total ms: 10' in output
    assert 'First token ms: 4' in output
