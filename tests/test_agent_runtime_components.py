from __future__ import annotations

from agent.agent import Agent
from agent import runtime_components


def test_approval_runtime_builds_and_snapshots_pending_approval():
    agent = Agent()
    result = {
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }

    payload = agent.approvals.build_payload(
        'curl_url',
        {'url': 'https://docs.python.org/3/'},
        result,
        'call-1',
    )
    agent.approvals.set('curl_url', {'url': 'https://docs.python.org/3/'}, result, 'call-1')

    expected = {
        'tool': 'curl_url',
        'call_id': 'call-1',
        'args': {'url': 'https://docs.python.org/3/'},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }
    assert payload == expected
    assert agent.approvals.snapshot() == expected


def test_approval_runtime_replace_and_clear_respect_approval_id():
    agent = Agent()
    original = {
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }
    replacement = {
        'approval_id': 'curl:cdn.example:456',
        'domain': 'cdn.example',
        'url': 'https://cdn.example/docs',
    }
    agent.approvals.set('curl_url', {'url': 'https://docs.python.org/3/'}, original, 'call-1')

    assert agent.approvals.replace(
        'curl:other:999',
        'curl_url',
        {'url': 'https://docs.python.org/3/'},
        replacement,
        'call-1',
    ) is False
    assert agent.approvals.snapshot()['approval_id'] == 'curl:docs.python.org:123'

    assert agent.approvals.replace(
        'curl:docs.python.org:123',
        'curl_url',
        {'url': 'https://docs.python.org/3/'},
        replacement,
        'call-1',
    ) is True
    assert agent.last_error == 'Waiting for user approval.'
    assert agent.approvals.snapshot()['approval_id'] == 'curl:cdn.example:456'

    assert agent.approvals.clear('curl:docs.python.org:123') is None
    cleared = agent.approvals.clear('curl:cdn.example:456')

    assert cleared is not None
    assert cleared['approval_id'] == 'curl:cdn.example:456'
    assert agent.approvals.snapshot() is None
    assert agent.last_error == ''


def test_generation_runtime_reserves_and_finishes_current_run():
    agent = Agent()

    run_id = agent.generation.reserve({'role': 'user', 'content': 'hello'})

    assert run_id == agent.run_id
    assert agent.generation.is_busy() is True
    assert agent.messages[-1] == {'role': 'user', 'content': 'hello'}
    assert agent.generation.reserve() is None

    agent.generation.finish(run_id)

    assert agent.generation.is_busy() is False


def test_generation_runtime_ignores_stale_finish():
    agent = Agent()
    run_id = agent.generation.reserve()
    assert run_id is not None

    agent.generation.finish(run_id - 1)

    assert agent.generation.is_busy() is True

    agent.generation.finish(run_id)
    assert agent.generation.is_busy() is False


def test_runner_component_delegates_to_run_loop(monkeypatch):
    agent = Agent()
    calls = []

    monkeypatch.setattr(
        runtime_components.run_loop,
        'call_model',
        lambda received_agent, run_id=None: calls.append((received_agent, run_id)) or 'ok',
    )

    assert agent.runner.call_model(7) == 'ok'
    assert calls == [(agent, 7)]
