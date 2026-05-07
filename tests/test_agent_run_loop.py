from __future__ import annotations

from types import SimpleNamespace

from agent import agent as agent_module
from agent.model_streaming import apply_content_delta, apply_tool_call_delta, consume_model_stream


def seed_messages(wallace, user_content: str = 'hello') -> None:
    wallace.messages = [
        {'role': 'system', 'content': 'base prompt'},
        {'role': 'user', 'content': user_content},
    ]


def disable_skill_selection(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_module,
        'request_skill_for_intent',
        lambda text: {'status': 'ok', 'skill_name': None, 'selection': {}},
    )


def test_call_model_removes_done_token_message(monkeypatch):
    disable_skill_selection(monkeypatch)
    wallace = agent_module.Agent()
    seed_messages(wallace)

    def fake_call_model_once(run_id):
        wallace.messages.append({'role': 'assistant', 'content': wallace.DONE})
        return {'role': 'assistant', 'content': wallace.DONE}

    monkeypatch.setattr(wallace, '_call_model_once', fake_call_model_once)

    assert wallace.call_model() == wallace.DONE
    assert wallace.messages[-1]['role'] == 'user'
    assert wallace.is_generating is False


def test_call_model_removes_empty_response_and_records_error(monkeypatch):
    disable_skill_selection(monkeypatch)
    wallace = agent_module.Agent()
    seed_messages(wallace)

    def fake_call_model_once(run_id):
        wallace.messages.append({'role': 'assistant', 'content': ''})
        return {'role': 'assistant', 'content': ''}

    monkeypatch.setattr(wallace, '_call_model_once', fake_call_model_once)

    assert wallace.call_model() is None
    assert wallace.last_error == 'Model returned an empty response.'
    assert wallace.messages[-1]['role'] == 'user'


def test_call_model_stops_after_max_auto_turns(monkeypatch):
    disable_skill_selection(monkeypatch)
    wallace = agent_module.Agent()
    wallace.MAX_AUTO_TURNS = 2
    seed_messages(wallace)

    monkeypatch.setattr(
        wallace,
        '_call_model_once',
        lambda run_id: {'role': 'assistant', 'content': '', 'tool_calls': [{'id': '1'}]},
    )
    monkeypatch.setattr(wallace, '_execute_callable', lambda tool_call, run_id: True)

    assert wallace.call_model() is None
    assert wallace.last_error == f'Stopped after 2 turns without receiving {wallace.DONE}.'
    assert wallace.messages[-1]['content'] == wallace.last_error


def test_call_model_executes_tool_calls_then_returns_content(monkeypatch):
    disable_skill_selection(monkeypatch)
    wallace = agent_module.Agent()
    seed_messages(wallace)
    calls = []
    responses = iter([
        {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'tool-1'}]},
        {'role': 'assistant', 'content': 'final answer'},
    ])

    monkeypatch.setattr(wallace, '_call_model_once', lambda run_id: next(responses))
    monkeypatch.setattr(wallace, '_execute_callable', lambda tool_call, run_id: calls.append(tool_call) or True)

    assert wallace.call_model() == 'final answer'
    assert calls == [{'id': 'tool-1'}]


def test_owasp_review_blocks_final_answer_until_reference_search(monkeypatch):
    monkeypatch.setattr(
        agent_module,
        'request_skill_for_intent',
        lambda text: {
            'status': 'ok',
            'skill_name': 'owasp_security_review',
            'allowed_tools': ['search_owasp_reference'],
            'recommended_tool_calls': [],
            'forbidden_tool_calls': [],
            'selection': {'forced': True},
        },
    )
    wallace = agent_module.Agent()
    seed_messages(wallace, 'review security of security_easy.py')
    responses = iter([
        {'role': 'assistant', 'content': 'Critical finding without OWASP retrieval'},
        {
            'role': 'assistant',
            'content': '',
            'tool_calls': [
                {
                    'id': 'tool-1',
                    'type': 'function',
                    'function': {
                        'name': 'search_owasp_reference',
                        'arguments': '{"query": "hardcoded secret"}',
                    },
                }
            ],
        },
        {'role': 'assistant', 'content': 'Critical finding with returned OWASP citation'},
    ])

    def fake_call_model_once(run_id):
        response = next(responses)
        wallace.messages.append(dict(response))
        return response

    def fake_execute(tool_call, run_id):
        wallace.owasp_reference_search_count += 1
        return True

    monkeypatch.setattr(wallace, '_call_model_once', fake_call_model_once)
    monkeypatch.setattr(wallace, '_execute_callable', fake_execute)

    assert wallace.call_model() == 'Critical finding with returned OWASP citation'
    assert wallace.owasp_reference_search_count == 1
    assert any(event.get('kind') == 'skill_policy' for event in wallace.tool_events)
    assert all(
        message.get('content') != 'Critical finding without OWASP retrieval'
        for message in wallace.messages
    )


def test_call_model_stops_when_tool_execution_reports_stale(monkeypatch):
    disable_skill_selection(monkeypatch)
    wallace = agent_module.Agent()
    seed_messages(wallace)

    monkeypatch.setattr(
        wallace,
        '_call_model_once',
        lambda run_id: {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'tool-1'}]},
    )
    monkeypatch.setattr(wallace, '_execute_callable', lambda tool_call, run_id: False)

    assert wallace.call_model() is None
    assert wallace.is_generating is False


def test_call_model_handles_skill_selection_failure(monkeypatch):
    def raise_selection(text):
        raise RuntimeError('selection failed')

    monkeypatch.setattr(agent_module, 'request_skill_for_intent', raise_selection)
    wallace = agent_module.Agent()
    seed_messages(wallace)
    monkeypatch.setattr(wallace, '_call_model_once', lambda run_id: {'role': 'assistant', 'content': 'ok'})

    assert wallace.call_model() == 'ok'
    assert wallace.tool_events[0]['kind'] == 'skill_selection'
    assert wallace.tool_events[0]['status'] == 'error'


def test_call_model_once_records_api_failure():
    wallace = agent_module.Agent()
    seed_messages(wallace)
    run_id = wallace.reserve_generation()
    assert run_id is not None

    class FailingCompletions:
        def create(self, **kwargs):
            raise RuntimeError('api failed')

    wallace.client = SimpleNamespace(chat=SimpleNamespace(completions=FailingCompletions()))

    response = wallace._call_model_once(run_id)

    assert response == {'role': 'assistant', 'content': '[Error: api failed]'}
    assert wallace.last_error == 'api failed'
    assert wallace.messages[-1]['content'] == '[Error: api failed]'


def test_prepare_model_call_injects_request_system_prompt():
    wallace = agent_module.Agent()
    seed_messages(wallace)
    wallace.request_system_prompt = 'request prompt'
    run_id = wallace.reserve_generation()
    assert run_id is not None

    prepared = wallace._prepare_model_call(run_id)
    wallace._finish_generation(run_id)

    assert prepared is not None
    request_messages, turn_index, model_call_index = prepared
    assert request_messages[0]['content'] == 'request prompt'
    assert turn_index == 0
    assert model_call_index == 0


def test_prepare_model_call_compacts_duplicate_tool_content():
    wallace = agent_module.Agent()
    repeated = '\n'.join(
        f'repeated line {index:02d} with enough detail to make alias compaction worthwhile'
        for index in range(1, 16)
    )
    wallace.messages = [
        {'role': 'system', 'content': 'base prompt'},
        {'role': 'user', 'content': 'hello'},
        {'role': 'tool', 'tool_call_id': 'call-1', 'content': repeated},
        {'role': 'tool', 'tool_call_id': 'call-2', 'content': repeated},
    ]
    run_id = wallace.reserve_generation()
    assert run_id is not None

    prepared = wallace._prepare_model_call(run_id)
    wallace._finish_generation(run_id)

    assert prepared is not None
    request_messages, _, _ = prepared
    assert request_messages[2]['content'].startswith('[CTXBLOCK msg=2 role=tool]')
    assert request_messages[3]['content'].startswith('[CTXREF msg=2 lines=1-15 hash=')
    assert wallace.messages[2]['content'] == repeated
    assert wallace.messages[3]['content'] == repeated
    request = wallace.metrics.snapshot()['current_request']
    assert request['context_reference_count'] == 1
    assert request['context_reference_saved_chars'] > 0
    assert request['uncompacted_prompt_chars'] > request['estimated_prompt_chars']


def test_prepare_model_call_traces_compaction_metadata(monkeypatch):
    wallace = agent_module.Agent()
    repeated = '\n'.join(
        f'trace line {index:02d} with enough detail to make alias compaction worthwhile'
        for index in range(1, 16)
    )
    events = []
    monkeypatch.setattr(wallace, '_trace', lambda event, **fields: events.append({'event': event, **fields}))
    wallace.messages = [
        {'role': 'system', 'content': 'base prompt'},
        {'role': 'user', 'content': 'hello'},
        {'role': 'tool', 'tool_call_id': 'call-1', 'content': repeated},
        {'role': 'tool', 'tool_call_id': 'call-2', 'content': repeated},
    ]
    run_id = wallace.reserve_generation()
    assert run_id is not None

    prepared = wallace._prepare_model_call(run_id)
    wallace._finish_generation(run_id)

    assert prepared is not None
    compaction_event = next(event for event in events if event['event'] == 'context_compaction_applied')
    assert compaction_event['reference_count'] == 1
    assert compaction_event['saved_chars'] > 0
    assert compaction_event['aliases'][0]['alias'].startswith('[CTXREF msg=2 lines=1-15 hash=')
    assert compaction_event['transforms'][0]['kind'] == 'source_numbered'
    assert compaction_event['transforms'][0]['has_ctxblock'] is True
    assert compaction_event['transforms'][1]['kind'] == 'target_aliased'
    assert compaction_event['transforms'][1]['has_ctxref'] is True


def test_call_model_once_sends_compacted_messages_to_api():
    wallace = agent_module.Agent()
    repeated = '\n'.join(
        f'api line {index:02d} with enough detail to make alias compaction worthwhile'
        for index in range(1, 16)
    )
    captured = {}

    class CapturingCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='ok', tool_calls=[]))])]

    wallace.client = SimpleNamespace(chat=SimpleNamespace(completions=CapturingCompletions()))
    wallace.messages = [
        {'role': 'system', 'content': 'base prompt'},
        {'role': 'user', 'content': 'hello'},
        {'role': 'tool', 'tool_call_id': 'call-1', 'content': repeated},
        {'role': 'tool', 'tool_call_id': 'call-2', 'content': repeated},
    ]
    run_id = wallace.reserve_generation()
    assert run_id is not None

    response = wallace._call_model_once(run_id)
    wallace._finish_generation(run_id)

    assert response == {'role': 'assistant', 'content': 'ok'}
    assert captured['messages'][2]['content'].startswith('[CTXBLOCK msg=2 role=tool]')
    assert captured['messages'][3]['content'].startswith('[CTXREF msg=2 lines=1-15 hash=')
    assert wallace.messages[2]['content'] == repeated
    assert wallace.messages[3]['content'] == repeated


def test_model_streaming_stops_on_stale_content_delta():
    wallace = agent_module.Agent()
    seed_messages(wallace)
    run_id = wallace.reserve_generation()
    assert run_id is not None
    assistant_message = {'role': 'assistant', 'content': ''}
    wallace.run_id += 1

    ok = apply_content_delta(wallace, run_id, 0, assistant_message, 'hello')

    assert ok is False
    assert assistant_message['content'] == ''


def test_model_streaming_stops_on_stale_tool_delta():
    wallace = agent_module.Agent()
    seed_messages(wallace)
    run_id = wallace.reserve_generation()
    assert run_id is not None
    assistant_message = {'role': 'assistant', 'content': ''}
    wallace.run_id += 1

    ok = apply_tool_call_delta(
        wallace,
        run_id,
        0,
        assistant_message,
        {},
        [SimpleNamespace(index=0, id='call', type='function', function=SimpleNamespace(name='read_file', arguments='{}'))],
    )

    assert ok is False
    assert 'tool_calls' not in assistant_message


def test_consume_model_stream_returns_false_when_delta_application_fails(monkeypatch):
    wallace = agent_module.Agent()
    seed_messages(wallace)
    run_id = wallace.reserve_generation()
    assert run_id is not None
    assistant_message = {'role': 'assistant', 'content': ''}

    chunk = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='hello', tool_calls=[]))])
    wallace.run_id += 1

    assert consume_model_stream(wallace, [chunk], run_id, 0, assistant_message) is False
