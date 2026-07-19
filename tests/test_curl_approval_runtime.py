from __future__ import annotations

from agent.agent import Agent
from agent import curl_approval
from agent.runtime import AgentRuntime
from tools.tool_registry import Tool


def pending_curl_approval() -> dict[str, object]:
    return {
        'tool': 'curl_url',
        'call_id': 'call-1',
        'args': {'url': 'https://docs.python.org/3/'},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }


def test_resolve_curl_approval_rejects_invalid_action():
    runtime = AgentRuntime(Agent())

    response = curl_approval.resolve_curl_approval(runtime, 'curl:docs.python.org:123', 'maybe')

    assert response.status_code == 400
    assert response.payload == {'ok': False, 'error': 'Action must be approve or deny'}


def test_resolve_curl_approval_rejects_missing_pending_approval():
    runtime = AgentRuntime(Agent())

    response = curl_approval.resolve_curl_approval(runtime, 'curl:docs.python.org:123', 'approve')

    assert response.status_code == 404
    assert response.payload == {'ok': False, 'error': 'No matching pending approval'}


def test_resolve_curl_approval_rejects_mismatched_pending_approval():
    runtime = AgentRuntime(Agent())
    runtime.agent.pending_approval = pending_curl_approval()

    response = curl_approval.resolve_curl_approval(runtime, 'curl:example.com:999', 'approve')

    assert response.status_code == 404
    assert response.payload == {'ok': False, 'error': 'No matching pending approval'}


def test_resolve_curl_approval_approve_persists_domain_and_resumes(monkeypatch):
    runtime = AgentRuntime(Agent())
    pending = pending_curl_approval()
    runtime.agent.pending_approval = dict(pending)
    added = []
    resumed = []
    monkeypatch.setattr(curl_approval, 'add_domain_to_whitelist', lambda domain: added.append(domain) or {'status': 'ok'})
    monkeypatch.setitem(
        curl_approval.TOOLS,
        'curl_url',
        Tool(
            'curl_url',
            lambda url: {
                'status': 'ok',
                'url': url,
                'final_url': url,
                'title': 'Docs',
                'content': 'text',
                'truncated': False,
            },
        ),
    )
    runtime.resume_with_resolved_tool_result = (
        lambda received_pending, tool_result, approval_id:
        resumed.append((received_pending, tool_result, approval_id)) or runtime.agent.approvals.clear(approval_id) or True
    )

    response = curl_approval.resolve_curl_approval(runtime, 'curl:docs.python.org:123', 'approve')

    assert response.status_code == 200
    assert response.payload == {'ok': True}
    assert added == ['docs.python.org']
    assert resumed == [
        (
            pending,
            {
                'status': 'ok',
                'url': 'https://docs.python.org/3/',
                'final_url': 'https://docs.python.org/3/',
                'title': 'Docs',
                'content': 'text',
                'truncated': False,
            },
            'curl:docs.python.org:123',
        )
    ]
    assert runtime.agent.pending_approval is None


def test_resolve_curl_approval_updates_pending_for_redirect_domain_without_resuming(monkeypatch):
    runtime = AgentRuntime(Agent())
    pending = pending_curl_approval()
    next_approval = {
        'status': 'approval_required',
        'approval_id': 'curl:cdn.example:456',
        'domain': 'cdn.example',
        'url': 'https://cdn.example/docs',
    }
    runtime.agent.pending_approval = dict(pending)
    added = []
    resumed = []
    monkeypatch.setattr(curl_approval, 'add_domain_to_whitelist', lambda domain: added.append(domain) or {'status': 'ok'})
    monkeypatch.setitem(curl_approval.TOOLS, 'curl_url', Tool('curl_url', lambda url: next_approval))
    runtime.resume_with_resolved_tool_result = (
        lambda received_pending, tool_result, approval_id:
        resumed.append((received_pending, tool_result, approval_id)) or True
    )

    response = curl_approval.resolve_curl_approval(runtime, 'curl:docs.python.org:123', 'approve')

    assert response.status_code == 200
    assert response.payload == {
        'ok': True,
        'pending_approval': {
            'tool': 'curl_url',
            'call_id': 'call-1',
            'args': {'url': 'https://docs.python.org/3/'},
            'approval_id': 'curl:cdn.example:456',
            'domain': 'cdn.example',
            'url': 'https://cdn.example/docs',
        },
    }
    assert added == ['docs.python.org']
    assert resumed == []
    assert runtime.agent.messages == runtime.agent._initial_messages()
    assert runtime.agent.last_error == 'Waiting for user approval.'


def test_resolve_curl_approval_rejects_invalid_redirect_approval_result(monkeypatch, caplog):
    runtime = AgentRuntime(Agent())
    pending = pending_curl_approval()
    runtime.agent.pending_approval = dict(pending)
    resumed = []
    monkeypatch.setattr(curl_approval, 'add_domain_to_whitelist', lambda domain: {'status': 'ok'})
    monkeypatch.setitem(
        curl_approval.TOOLS,
        'curl_url',
        Tool('curl_url', lambda url: {'status': 'approval_required', 'url': 'https://cdn.example/docs'}),
    )
    runtime.resume_with_resolved_tool_result = (
        lambda received_pending, tool_result, approval_id:
        resumed.append((received_pending, tool_result, approval_id)) or True
    )

    with caplog.at_level('ERROR', logger='agent.curl_approval'):
        response = curl_approval.resolve_curl_approval(runtime, 'curl:docs.python.org:123', 'approve')

    assert response.status_code == 500
    assert response.payload == {
        'ok': False,
        'error': 'Curl approval result failed contract validation.',
    }
    assert resumed == []
    assert runtime.agent.pending_approval == pending
    assert 'curl approval tool result contract validation failed' in caplog.text


def test_resolve_curl_approval_deny_appends_denial_and_resumes():
    runtime = AgentRuntime(Agent())
    pending = pending_curl_approval()
    runtime.agent.pending_approval = dict(pending)
    resumed = []
    runtime.resume_with_resolved_tool_result = (
        lambda received_pending, tool_result, approval_id:
        resumed.append((received_pending, tool_result, approval_id)) or runtime.agent.approvals.clear(approval_id) or True
    )

    response = curl_approval.resolve_curl_approval(runtime, 'curl:docs.python.org:123', 'deny')

    assert response.status_code == 200
    assert response.payload == {'ok': True}
    assert resumed == [
        (
            pending,
            {
                'status': 'error',
                'url': 'https://docs.python.org/3/',
                'domain': 'docs.python.org',
                'error': 'domain is not whitelisted',
                'message': 'The user denied adding this domain to the curl whitelist.',
            },
            'curl:docs.python.org:123',
        )
    ]
    assert runtime.agent.pending_approval is None


def test_resolve_curl_approval_keeps_pending_when_persist_fails(monkeypatch):
    runtime = AgentRuntime(Agent())
    pending = pending_curl_approval()
    runtime.agent.pending_approval = dict(pending)
    monkeypatch.setattr(curl_approval, 'add_domain_to_whitelist', lambda domain: {'status': 'error', 'error': 'disk full'})

    response = curl_approval.resolve_curl_approval(runtime, 'curl:docs.python.org:123', 'approve')

    assert response.status_code == 500
    assert response.payload == {'ok': False, 'error': 'disk full'}
    assert runtime.agent.pending_approval == pending


def test_resolve_curl_approval_rejects_missing_tool(monkeypatch):
    runtime = AgentRuntime(Agent())
    pending = pending_curl_approval()
    runtime.agent.pending_approval = dict(pending)
    monkeypatch.setattr(curl_approval, 'add_domain_to_whitelist', lambda domain: {'status': 'ok'})
    monkeypatch.delitem(curl_approval.TOOLS, 'curl_url')

    response = curl_approval.resolve_curl_approval(runtime, 'curl:docs.python.org:123', 'approve')

    assert response.status_code == 500
    assert response.payload == {'ok': False, 'error': 'Pending tool is no longer registered'}
    assert runtime.agent.pending_approval == pending


def test_resolve_curl_approval_keeps_pending_when_resume_is_busy(monkeypatch):
    runtime = AgentRuntime(Agent())
    pending = pending_curl_approval()
    runtime.agent.pending_approval = dict(pending)
    monkeypatch.setattr(curl_approval, 'add_domain_to_whitelist', lambda domain: {'status': 'ok'})
    monkeypatch.setitem(
        curl_approval.TOOLS,
        'curl_url',
        Tool('curl_url', lambda url: {'status': 'ok', 'url': url, 'content': 'text'}),
    )
    runtime.resume_with_resolved_tool_result = lambda received_pending, tool_result, approval_id: False

    response = curl_approval.resolve_curl_approval(runtime, 'curl:docs.python.org:123', 'approve')

    assert response.status_code == 409
    assert response.payload == {'ok': False, 'error': 'Generation already in progress'}
    assert runtime.agent.pending_approval == pending
    assert runtime.agent.messages == runtime.agent._initial_messages()
