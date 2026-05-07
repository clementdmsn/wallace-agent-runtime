from __future__ import annotations

from agent.agent_metrics import AgentMetrics, estimate_messages_chars


def test_agent_metrics_records_request_model_and_tool():
    metrics = AgentMetrics()
    metrics.start_request(7, 'model-a', 120)
    call_index = metrics.start_model_call(
        7,
        0,
        'model-a',
        180,
        uncompacted_prompt_chars=240,
        compaction_stats={'context_reference_count': 2, 'context_reference_saved_chars': 60},
    )
    metrics.mark_first_output(7, call_index, 'content')
    metrics.finish_model_call(7, call_index)
    metrics.record_tool_call(7, 'read_file', 'ok', 12.345)
    metrics.finish_request(7)

    snapshot = metrics.snapshot()
    request = snapshot['last_request']

    assert request['id'] == 7
    assert request['estimated_system_prompt_chars'] == 120
    assert request['estimated_prompt_chars'] == 180
    assert request['uncompacted_prompt_chars'] == 240
    assert request['context_reference_count'] == 2
    assert request['context_reference_saved_chars'] == 60
    assert request['auto_turns'] == 1
    assert request['tool_call_count'] == 1
    assert request['model_calls'][0]['uncompacted_prompt_chars'] == 240
    assert request['model_calls'][0]['context_reference_count'] == 2
    assert request['model_calls'][0]['ttft_ms'] is not None
    assert request['model_calls'][0]['model_total_ms'] is not None
    assert request['tool_calls'] == [{'tool': 'read_file', 'status': 'ok', 'duration_ms': 12.35}]


def test_estimate_messages_chars_counts_content_and_tool_calls():
    count = estimate_messages_chars([
        {'role': 'system', 'content': 'abc'},
        {'role': 'assistant', 'content': '', 'tool_calls': [{'id': '1'}]},
    ])

    assert count >= len('systemabcassistant')


def test_agent_metrics_snapshot_includes_running_elapsed_time():
    metrics = AgentMetrics()
    metrics.start_request(7, 'model-a', 120)
    metrics.start_model_call(7, 0, 'model-a', 240)

    request = metrics.snapshot()['current_request']

    assert request['request_elapsed_ms'] >= 0
    assert request['model_calls'][0]['model_elapsed_ms'] >= 0
