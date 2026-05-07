from __future__ import annotations

from web import web_app
from web.metrics_routes import measure_baseline
from tools.tool_registry import Tool


class Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class Choice:
    def __init__(self, delta):
        self.delta = delta


class Chunk:
    def __init__(self, delta):
        self.choices = [Choice(delta)]


class FakeCompletions:
    def __init__(self, stream):
        self.stream = stream
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.stream


class FakeClient:
    def __init__(self, stream):
        self.chat = type('Chat', (), {})()
        self.chat.completions = FakeCompletions(stream)


def reset_web_agent() -> None:
    with web_app.agent.lock:
        web_app.agent.messages = web_app.agent._initial_messages()
        web_app.agent.tool_events = []
        web_app.agent.is_generating = False
        web_app.agent.last_error = ''
        web_app.agent.pending_approval = None
        web_app.agent.metrics.reset_current()
        web_app.agent._reset_skill_state()


def set_agent_busy(is_busy: bool = True) -> None:
    with web_app.agent.lock:
        web_app.agent.is_generating = is_busy


def seed_agent_state(
    messages=None,
    tool_events=None,
    last_error: str = '',
) -> None:
    with web_app.agent.lock:
        if messages is not None:
            web_app.agent.messages = messages
        if tool_events is not None:
            web_app.agent.tool_events = tool_events
        web_app.agent.last_error = last_error


def setup_function():
    web_app.worker = None
    reset_web_agent()


def test_health_route_returns_ok():
    client = web_app.app.test_client()

    response = client.get('/api/health')

    assert response.status_code == 200
    assert response.get_json() == {'ok': True}


def test_metrics_js_route_returns_script():
    client = web_app.app.test_client()

    response = client.get('/metrics.js')

    assert response.status_code == 200
    assert b'renderRuntimeMetrics' in response.data


def test_state_hides_system_and_tool_messages():
    client = web_app.app.test_client()
    seed_agent_state(
        messages=[
            {'role': 'system', 'content': 'hidden'},
            {'role': 'user', 'content': 'hello'},
            {'role': 'tool', 'content': 'hidden tool'},
            {'role': 'assistant', 'content': 'hi'},
            {'role': 'assistant', 'content': '', 'tool_calls': [{'id': '1'}]},
        ],
        tool_events=[{'kind': 'tool', 'tool': 'read_file', 'result': {'status': 'ok'}}],
    )

    response = client.get('/api/state')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['messages'] == [
        {'role': 'user', 'content': 'hello'},
        {'role': 'assistant', 'content': 'hi'},
    ]
    assert payload['tool_events'] == [{'kind': 'tool', 'tool': 'read_file', 'result': {'status': 'ok'}}]
    assert 'runtime_metrics' in payload
    assert payload['active_skill_name'] is None
    assert payload['active_skill_policy'] == {}
    assert payload['is_generating'] is False
    assert payload['pending_approval'] is None


def test_state_includes_active_skill_policy():
    client = web_app.app.test_client()
    with web_app.agent.lock:
        web_app.agent.active_skill_name = 'owasp_security_review'
        web_app.agent.active_skill_policy = {
            'allowed_tools': ['discover_review_targets', 'search_owasp_reference'],
            'recommended_tool_calls': [{'tool': 'discover_review_targets'}],
            'forbidden_tool_calls': [],
        }

    response = client.get('/api/state')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['active_skill_name'] == 'owasp_security_review'
    assert payload['active_skill_policy']['allowed_tools'] == [
        'discover_review_targets',
        'search_owasp_reference',
    ]


def test_state_includes_pending_curl_approval():
    client = web_app.app.test_client()
    with web_app.agent.lock:
        web_app.agent.pending_approval = {
            'tool': 'curl_url',
            'approval_id': 'curl:docs.python.org:123',
            'domain': 'docs.python.org',
            'url': 'https://docs.python.org/3/',
        }

    response = client.get('/api/state')

    assert response.status_code == 200
    assert response.get_json()['pending_approval'] == {
        'tool': 'curl_url',
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }


def test_post_message_rejects_empty_content():
    client = web_app.app.test_client()

    response = client.post('/api/messages', json={'content': '   '})

    assert response.status_code == 400
    assert response.get_json()['error'] == 'Empty message'


def test_post_message_rejects_while_generation_is_active():
    client = web_app.app.test_client()
    set_agent_busy()

    response = client.post('/api/messages', json={'content': 'hello'})

    assert response.status_code == 409
    assert response.get_json()['error'] == 'Generation already in progress'


def test_post_message_adds_user_message_and_starts_generation(monkeypatch):
    client = web_app.app.test_client()
    started = []

    def fake_start_generation(submitted) -> bool:
        web_app.agent.add_message(submitted)
        started.append(submitted)
        return True

    monkeypatch.setattr(web_app, 'start_generation', fake_start_generation)

    response = client.post('/api/messages', json={'content': ' hello '})

    assert response.status_code == 200
    assert response.get_json() == {'ok': True}
    assert started == [{'role': 'user', 'content': 'hello'}]
    assert web_app.agent.messages[-1] == {'role': 'user', 'content': 'hello'}


def test_post_message_does_not_append_when_generation_start_is_rejected(monkeypatch):
    client = web_app.app.test_client()

    monkeypatch.setattr(web_app, 'start_generation', lambda submitted: False)

    response = client.post('/api/messages', json={'content': 'hello'})

    assert response.status_code == 409
    assert response.get_json()['error'] == 'Generation already in progress'
    assert web_app.agent.messages == web_app.agent._initial_messages()


def test_reset_rejects_while_generation_is_active():
    client = web_app.app.test_client()
    set_agent_busy()

    response = client.post('/api/reset')

    assert response.status_code == 409
    assert response.get_json()['error'] == 'Generation in progress'


def test_reset_does_not_allow_get():
    client = web_app.app.test_client()

    response = client.get('/api/reset')

    assert response.status_code == 405


def test_reset_clears_visible_conversation_when_idle():
    client = web_app.app.test_client()
    seed_agent_state(
        messages=[
            *web_app.agent._initial_messages(),
            {'role': 'user', 'content': 'hello'},
        ],
        tool_events=[{'kind': 'tool'}],
        last_error='boom',
    )

    response = client.post('/api/reset')

    assert response.status_code == 200
    assert response.get_json() == {'ok': True}

    state = client.get('/api/state').get_json()
    assert state['messages'] == []
    assert state['tool_events'] == []
    assert state['last_error'] == ''


def test_baseline_metrics_rejects_while_generation_is_active():
    client = web_app.app.test_client()
    set_agent_busy()

    response = client.post('/api/metrics/baseline')

    assert response.status_code == 409
    assert response.get_json()['error'] == 'Generation already in progress'


def test_baseline_metrics_reserves_runtime_during_measurement():
    runtime = web_app.WallaceRuntime(web_app.Agent())
    overlap_attempts = []

    class OverlapStream:
        def __iter__(self):
            overlap_attempts.append(runtime.start_generation({'role': 'user', 'content': 'overlap'}))
            return iter([Chunk(Delta(content='O'))])

    runtime.agent.client = FakeClient(OverlapStream())
    client = web_app.create_app(runtime).test_client()

    response = client.post('/api/metrics/baseline')

    assert response.status_code == 200
    assert overlap_attempts == [False]
    assert runtime.agent.is_busy() is False
    assert runtime.agent.messages == runtime.agent._initial_messages()


def test_measure_baseline_records_content_ttft():
    agent = web_app.Agent()
    agent.client = FakeClient([Chunk(Delta(content='O'))])

    result = measure_baseline(agent)

    assert result['status'] == 'ok'
    assert result['first_output_kind'] == 'content'
    assert result['baseline_ttft_ms'] is not None
    assert agent.metrics.snapshot()['baseline']['status'] == 'ok'
    call = agent.client.chat.completions.calls[0]
    assert call['max_tokens'] == 1
    assert call['stream'] is True


def test_measure_baseline_records_tool_call_ttft():
    agent = web_app.Agent()
    agent.client = FakeClient([Chunk(Delta(tool_calls=[object()]))])

    result = measure_baseline(agent)

    assert result['status'] == 'ok'
    assert result['first_output_kind'] == 'tool_call'


def test_baseline_metrics_route_records_errors():
    runtime = web_app.WallaceRuntime(web_app.Agent())

    class RaisingCompletions:
        def create(self, **kwargs):
            raise RuntimeError('baseline failed')

    runtime.agent.client = type('Client', (), {})()
    runtime.agent.client.chat = type('Chat', (), {})()
    runtime.agent.client.chat.completions = RaisingCompletions()
    client = web_app.create_app(runtime).test_client()

    response = client.post('/api/metrics/baseline')

    assert response.status_code == 500
    assert response.get_json() == {'status': 'error', 'error': 'baseline failed'}
    assert runtime.agent.metrics.snapshot()['baseline']['error'] == 'baseline failed'


def test_create_app_can_use_isolated_runtime():
    isolated_runtime = web_app.WallaceRuntime(web_app.Agent())
    started = []
    isolated_app = web_app.create_app(
        isolated_runtime,
        start_generation_func=lambda submitted: started.append(submitted) or True,
    )
    client = isolated_app.test_client()

    response = client.post('/api/messages', json={'content': 'isolated'})

    assert response.status_code == 200
    assert started == [{'role': 'user', 'content': 'isolated'}]
    assert web_app.agent.messages == web_app.agent._initial_messages()


def test_runtime_resume_with_tool_result_clears_pending_after_reserving_generation():
    runtime = web_app.WallaceRuntime(web_app.Agent())
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
    runtime.agent.pending_approval = dict(pending)

    def finish_immediately(run_id):
        runtime.agent._finish_generation(run_id)

    runtime.agent.call_model = finish_immediately

    resumed = runtime.resume_with_resolved_tool_result(
        pending,
        tool_result,
        'curl:docs.python.org:123',
    )
    runtime.worker.join(timeout=1)

    assert resumed is True
    assert runtime.agent.pending_approval is None
    assert runtime.agent.messages[-1]['role'] == 'tool'
    hidden = runtime.agent.messages[-1]['content']
    assert '"status": "ok"' in hidden
    assert '"content": "text"' in hidden
    assert runtime.agent.is_busy() is False


def test_curl_approval_approve_persists_domain_and_resumes(monkeypatch):
    runtime = web_app.WallaceRuntime(web_app.Agent())
    pending = {
        'tool': 'curl_url',
        'call_id': 'call-1',
        'args': {'url': 'https://docs.python.org/3/'},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }
    runtime.agent.pending_approval = dict(pending)
    added = []
    resumed = []
    monkeypatch.setattr(web_app, 'add_domain_to_whitelist', lambda domain: added.append(domain) or {'status': 'ok'})
    monkeypatch.setitem(
        web_app.TOOLS,
        'curl_url',
        Tool('curl_url', lambda url: {'status': 'ok', 'url': url, 'final_url': url, 'title': 'Docs', 'content': 'text', 'truncated': False}),
    )
    runtime.resume_with_resolved_tool_result = (
        lambda received_pending, tool_result, approval_id:
        resumed.append((received_pending, tool_result, approval_id)) or runtime.agent.clear_pending_approval(approval_id) or True
    )
    client = web_app.create_app(runtime).test_client()

    response = client.post(
        '/api/curl-approvals',
        json={'approval_id': 'curl:docs.python.org:123', 'action': 'approve'},
    )

    assert response.status_code == 200
    assert response.get_json() == {'ok': True}
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


def test_curl_approval_updates_pending_for_redirect_domain_without_resuming(monkeypatch):
    runtime = web_app.WallaceRuntime(web_app.Agent())
    pending = {
        'tool': 'curl_url',
        'call_id': 'call-1',
        'args': {'url': 'https://docs.python.org/3/'},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }
    next_approval = {
        'status': 'approval_required',
        'approval_id': 'curl:cdn.example:456',
        'domain': 'cdn.example',
        'url': 'https://cdn.example/docs',
    }
    runtime.agent.pending_approval = dict(pending)
    added = []
    resumed = []
    monkeypatch.setattr(web_app, 'add_domain_to_whitelist', lambda domain: added.append(domain) or {'status': 'ok'})
    monkeypatch.setitem(web_app.TOOLS, 'curl_url', Tool('curl_url', lambda url: next_approval))
    runtime.resume_with_resolved_tool_result = (
        lambda received_pending, tool_result, approval_id:
        resumed.append((received_pending, tool_result, approval_id)) or True
    )
    client = web_app.create_app(runtime).test_client()

    response = client.post(
        '/api/curl-approvals',
        json={'approval_id': 'curl:docs.python.org:123', 'action': 'approve'},
    )

    assert response.status_code == 200
    assert response.get_json() == {
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


def test_curl_approval_deny_appends_denial_and_resumes():
    runtime = web_app.WallaceRuntime(web_app.Agent())
    pending = {
        'tool': 'curl_url',
        'call_id': 'call-1',
        'args': {'url': 'https://docs.python.org/3/'},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }
    runtime.agent.pending_approval = dict(pending)
    resumed = []
    runtime.resume_with_resolved_tool_result = (
        lambda received_pending, tool_result, approval_id:
        resumed.append((received_pending, tool_result, approval_id)) or runtime.agent.clear_pending_approval(approval_id) or True
    )
    client = web_app.create_app(runtime).test_client()

    response = client.post(
        '/api/curl-approvals',
        json={'approval_id': 'curl:docs.python.org:123', 'action': 'deny'},
    )

    assert response.status_code == 200
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


def test_curl_approval_keeps_pending_when_persist_fails(monkeypatch):
    runtime = web_app.WallaceRuntime(web_app.Agent())
    pending = {
        'tool': 'curl_url',
        'call_id': 'call-1',
        'args': {'url': 'https://docs.python.org/3/'},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }
    runtime.agent.pending_approval = dict(pending)
    monkeypatch.setattr(web_app, 'add_domain_to_whitelist', lambda domain: {'status': 'error', 'error': 'disk full'})
    client = web_app.create_app(runtime).test_client()

    response = client.post(
        '/api/curl-approvals',
        json={'approval_id': 'curl:docs.python.org:123', 'action': 'approve'},
    )

    assert response.status_code == 500
    assert response.get_json()['error'] == 'disk full'
    assert runtime.agent.pending_approval == pending


def test_curl_approval_rejects_missing_pending_approval():
    runtime = web_app.WallaceRuntime(web_app.Agent())
    client = web_app.create_app(runtime).test_client()

    response = client.post(
        '/api/curl-approvals',
        json={'approval_id': 'curl:docs.python.org:123', 'action': 'approve'},
    )

    assert response.status_code == 404


def test_curl_approval_keeps_pending_when_resume_is_busy(monkeypatch):
    runtime = web_app.WallaceRuntime(web_app.Agent())
    pending = {
        'tool': 'curl_url',
        'call_id': 'call-1',
        'args': {'url': 'https://docs.python.org/3/'},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }
    runtime.agent.pending_approval = dict(pending)
    monkeypatch.setattr(web_app, 'add_domain_to_whitelist', lambda domain: {'status': 'ok'})
    monkeypatch.setitem(
        web_app.TOOLS,
        'curl_url',
        Tool('curl_url', lambda url: {'status': 'ok', 'url': url, 'content': 'text'}),
    )
    runtime.resume_with_resolved_tool_result = lambda received_pending, tool_result, approval_id: False
    client = web_app.create_app(runtime).test_client()

    response = client.post(
        '/api/curl-approvals',
        json={'approval_id': 'curl:docs.python.org:123', 'action': 'approve'},
    )

    assert response.status_code == 409
    assert runtime.agent.pending_approval == pending
    assert runtime.agent.messages == runtime.agent._initial_messages()
