from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.agent import Agent
from agent.runtime import AgentRuntime


def test_snapshot_state_hides_non_visible_messages_and_tool_call_placeholders():
    runtime = AgentRuntime(Agent())
    runtime.agent.messages = [
        {'role': 'system', 'content': 'hidden'},
        {'role': 'user', 'content': 'hello'},
        {'role': 'tool', 'content': 'hidden tool'},
        {'role': 'developer', 'content': 'hidden developer'},
        {'role': 'assistant', 'content': 'hi'},
        {'role': 'assistant', 'content': '', 'tool_calls': [{'id': '1'}]},
    ]
    runtime.agent.tool_events = [
        {'kind': 'tool', 'tool': 'read_file', 'result': {'status': 'ok'}},
    ]

    payload = runtime.snapshot_state().to_payload()

    assert payload['messages'] == [
        {'role': 'user', 'content': 'hello'},
        {'role': 'assistant', 'content': 'hi'},
    ]
    assert payload['tool_events'] == [
        {
            'id': '',
            'kind': 'tool',
            'args': {},
            'tool': 'read_file',
            'result': {'status': 'ok'},
        }
    ]
    assert payload['runtime_metrics'] == runtime.agent.metrics.snapshot()
    assert payload['active_skill_name'] is None
    assert payload['active_skill_policy'] == {}
    assert payload['is_generating'] is False
    assert payload['last_error'] == ''
    assert payload['pending_approval'] is None


def test_snapshot_state_includes_skill_state_and_pending_approval():
    runtime = AgentRuntime(Agent())
    runtime.agent.active_skill_name = 'owasp_security_review'
    runtime.agent.active_skill_policy = {
        'allowed_tools': ['discover_review_targets', 'search_owasp_reference'],
        'recommended_tool_calls': [{'tool': 'discover_review_targets'}],
        'forbidden_tool_calls': [],
    }
    runtime.agent.pending_approval = {
        'tool': 'curl_url',
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }

    payload = runtime.snapshot_state().to_payload()

    assert payload['active_skill_name'] == 'owasp_security_review'
    assert payload['active_skill_policy']['allowed_tools'] == [
        'discover_review_targets',
        'search_owasp_reference',
    ]
    assert payload['pending_approval'] == {
        'tool': 'curl_url',
        'call_id': '',
        'args': {},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }


def test_start_generation_reserves_message_and_starts_worker(monkeypatch):
    runtime = AgentRuntime(Agent())
    calls = []

    def finish_immediately(run_id):
        calls.append(run_id)
        runtime.agent.generation.finish(run_id)

    monkeypatch.setattr(runtime.agent, 'call_model', finish_immediately)

    started = runtime.start_generation({'role': 'user', 'content': 'hello'})
    runtime.worker.join(timeout=1)

    assert started is True
    assert calls == [runtime.agent.run_id]
    assert runtime.agent.messages[-1] == {'role': 'user', 'content': 'hello'}
    assert runtime.agent.generation.is_busy() is False


def test_start_generation_rejects_concurrent_generation(monkeypatch):
    runtime = AgentRuntime(Agent())
    calls = []

    monkeypatch.setattr(runtime.agent, 'call_model', lambda run_id: calls.append(run_id))

    assert runtime.start_generation({'role': 'user', 'content': 'first'}) is True
    runtime.worker.join(timeout=1)

    assert runtime.start_generation({'role': 'user', 'content': 'second'}) is False
    assert calls == [runtime.agent.run_id]
    assert runtime.agent.messages[-1] == {'role': 'user', 'content': 'first'}

    runtime.agent.generation.finish(runtime.agent.run_id)


def test_resume_with_resolved_tool_result_clears_pending_and_starts_worker(monkeypatch):
    runtime = AgentRuntime(Agent())
    pending = {
        'tool': 'curl_url',
        'call_id': 'call-1',
        'args': {'url': 'https://docs.python.org/3/'},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }
    tool_result = {
        'status': 'ok',
        'url': 'https://docs.python.org/3/',
        'final_url': 'https://docs.python.org/3/',
        'content': 'text',
    }
    calls = []
    runtime.agent.pending_approval = dict(pending)

    def finish_immediately(run_id):
        calls.append(run_id)
        runtime.agent.generation.finish(run_id)

    monkeypatch.setattr(runtime.agent, 'call_model', finish_immediately)

    resumed = runtime.resume_with_resolved_tool_result(
        pending,
        tool_result,
        'curl:docs.python.org:123',
    )
    runtime.worker.join(timeout=1)

    assert resumed is True
    assert calls == [runtime.agent.run_id]
    assert runtime.agent.pending_approval is None
    assert runtime.agent.messages[-1]['role'] == 'tool'
    assert runtime.agent.generation.is_busy() is False


@pytest.mark.parametrize(
    'tool_events,pending_approval',
    [
        ([{'kind': 'skill_policy', 'status': 'ok'}], None),
        (
            [],
            {
                'tool': 'curl_url',
                'approval_id': 'curl:docs.python.org:123',
            },
        ),
    ],
)
def test_snapshot_state_propagates_contract_validation_errors(tool_events, pending_approval):
    runtime = AgentRuntime(Agent())
    runtime.agent.tool_events = tool_events
    runtime.agent.pending_approval = pending_approval

    with pytest.raises(ValidationError):
        runtime.snapshot_state()
