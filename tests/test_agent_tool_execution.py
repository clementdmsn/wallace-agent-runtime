from __future__ import annotations

import json
import threading

from agent import agent_tool_execution
from tools.tool_registry import Tool


class FakeAgent:
    def __init__(self):
        self.lock = threading.RLock()
        self.messages = []
        self.tool_events = []
        self.active_skill_name = None
        self.active_skill_policy = {}
        self.skill_tool_call_index = 0
        self.skill_creation_failures = 0
        self.verified_symbols_by_path = {}
        self.metrics = None
        self.last_error = ''
        self.trace_events = []
        self.run_trace = None
        self.notifications = 0
        self.pending_approval = None

    def _is_current_run(self, run_id: int) -> bool:
        return run_id == 7

    def _notify_stream(self) -> None:
        self.notifications += 1

    def _trace(self, event: str, **fields) -> None:
        self.trace_events.append({'event': event, **fields})

    def set_pending_approval(self, tool_name, args, result, call_id='') -> None:
        self.pending_approval = {
            'tool': tool_name,
            'call_id': call_id,
            'args': dict(args),
            'approval_id': result.get('approval_id'),
            'domain': result.get('domain'),
            'url': result.get('url') or args.get('url'),
        }


def tool_call(name: str, arguments: str = '{}') -> dict[str, object]:
    return {
        'id': 'call-1',
        'function': {
            'name': name,
            'arguments': arguments,
        },
    }


def test_execute_tool_call_records_invalid_json_as_tool_error():
    agent = FakeAgent()

    ok = agent_tool_execution.execute_tool_call(agent, tool_call('read_file', '{bad json'), 7)

    assert ok is True
    assert agent.tool_events[0]['result']['status'] == 'error'
    assert 'invalid call arguments' in agent.tool_events[0]['result']['error']
    hidden = agent.messages[0]
    assert hidden['role'] == 'tool'
    assert json.loads(hidden['content'])['status'] == 'error'


def test_execute_tool_call_records_unknown_tool_error():
    agent = FakeAgent()

    ok = agent_tool_execution.execute_tool_call(agent, tool_call('missing_tool'), 7)

    assert ok is True
    assert agent.tool_events[0]['result'] == {
        'status': 'error',
        'error': 'unknown tool: missing_tool',
        'message': 'Only registered tools are executable.',
    }


def test_execute_tool_call_runs_registered_tool_and_appends_hidden_message(monkeypatch):
    agent = FakeAgent()

    def fake_tool(path: str) -> dict[str, object]:
        return {'status': 'ok', 'path': path, 'content': 'hello'}

    monkeypatch.setitem(agent_tool_execution.TOOLS, 'fake_read', Tool('fake_read', fake_tool))

    ok = agent_tool_execution.execute_tool_call(
        agent,
        tool_call('fake_read', json.dumps({'path': 'notes.txt'})),
        7,
    )

    assert ok is True
    assert agent.tool_events == [
        {
            'id': 'call-1',
            'kind': 'tool',
            'tool': 'fake_read',
            'args': {'path': 'notes.txt'},
            'result': {'status': 'ok', 'path': 'notes.txt', 'content': 'hello'},
        }
    ]
    hidden = agent.messages[0]
    assert hidden['role'] == 'tool'
    assert hidden['tool_call_id'] == 'call-1'
    assert json.loads(hidden['content']) == {
        'tool': 'fake_read',
        'status': 'ok',
        'path': 'notes.txt',
        'content': 'hello',
    }
    assert agent.notifications == 1
    assert agent.trace_events[0]['event'] == 'tool_call_started'
    assert agent.trace_events[0]['raw_arguments'] == json.dumps({'path': 'notes.txt'})
    assert agent.trace_events[-1]['event'] == 'tool_call_finished'
    assert agent.trace_events[-1]['tool'] == 'fake_read'
    assert agent.trace_events[-1]['status'] == 'ok'
    assert agent.trace_events[-1]['args'] == {'path': 'notes.txt'}
    assert agent.trace_events[-1]['result'] == {'status': 'ok', 'path': 'notes.txt', 'content': 'hello'}


def test_hidden_tool_message_includes_truncation_metadata(monkeypatch):
    agent = FakeAgent()

    def fake_tool() -> dict[str, object]:
        return {
            'status': 'ok',
            'stdout': '12345',
            'stdout_truncated': True,
            'stderr': '',
            'stderr_truncated': False,
        }

    monkeypatch.setitem(agent_tool_execution.TOOLS, 'fake_shell', Tool('fake_shell', fake_tool))

    ok = agent_tool_execution.execute_tool_call(agent, tool_call('fake_shell'), 7)

    hidden = json.loads(agent.messages[0]['content'])
    assert ok is True
    assert hidden['stdout_truncated'] is True
    assert hidden['stderr_truncated'] is False


def test_execute_tool_call_stops_run_for_pending_approval(monkeypatch):
    agent = FakeAgent()

    def fake_curl(url: str) -> dict[str, object]:
        return {
            'status': 'approval_required',
            'url': url,
            'domain': 'docs.python.org',
            'approval_id': 'curl:docs.python.org:123',
        }

    monkeypatch.setitem(agent_tool_execution.TOOLS, 'curl_url', Tool('curl_url', fake_curl))

    ok = agent_tool_execution.execute_tool_call(
        agent,
        tool_call('curl_url', json.dumps({'url': 'https://docs.python.org/3/'})),
        7,
    )

    assert ok is False
    assert agent.pending_approval == {
        'tool': 'curl_url',
        'call_id': 'call-1',
        'args': {'url': 'https://docs.python.org/3/'},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }
    assert agent.last_error == 'Waiting for user approval.'
    assert agent.messages == []


def test_execute_tool_call_does_not_mutate_stale_run(monkeypatch):
    agent = FakeAgent()
    called = []

    monkeypatch.setitem(
        agent_tool_execution.TOOLS,
        'fake_tool',
        Tool('fake_tool', lambda: called.append(True) or {'status': 'ok'}),
    )

    ok = agent_tool_execution.execute_tool_call(agent, tool_call('fake_tool'), 99)

    assert ok is False
    assert called == []
    assert agent.tool_events == []
    assert agent.messages == []


def test_execute_tool_call_records_tool_duration(monkeypatch):
    agent = FakeAgent()
    recorded = []

    class Metrics:
        def record_tool_call(self, run_id, tool, status, duration_ms):
            recorded.append((run_id, tool, status, duration_ms))

    agent.metrics = Metrics()
    monkeypatch.setitem(
        agent_tool_execution.TOOLS,
        'fake_tool',
        Tool('fake_tool', lambda: {'status': 'ok'}),
    )

    ok = agent_tool_execution.execute_tool_call(agent, tool_call('fake_tool'), 7)

    assert ok is True
    assert recorded
    assert recorded[0][0:3] == (7, 'fake_tool', 'ok')
    assert recorded[0][3] >= 0


def test_execute_tool_call_returns_create_skill_draft_after_three_validation_failures(monkeypatch):
    agent = FakeAgent()

    def fake_create_skill(title, markdown, json_payload):
        return {
            'status': 'error',
            'error': 'json_payload failed skill quality validation',
            'validation_errors': [{'field': 'inputs', 'message': 'bad input'}],
            'repair_instructions': ['Use path.'],
            'repair_suggestions': [{'field': 'inputs', 'replace': 'file_path', 'with': 'path'}],
            'draft_id': 'demo',
            'draft_metadata_path': 'skills/drafts/demo.json',
            'draft_procedure_path': 'skills/drafts/demo.md',
            'retry_policy': 'Retry briefly.',
        }

    monkeypatch.setitem(agent_tool_execution.TOOLS, 'create_skill', Tool('create_skill', fake_create_skill))
    args = {
        'title': 'demo',
        'markdown': 'procedure',
        'json_payload': {'name': 'demo'},
    }

    for _ in range(3):
        ok = agent_tool_execution.execute_tool_call(agent, tool_call('create_skill', json.dumps(args)), 7)

    assert ok is True
    result = agent.tool_events[-1]['result']
    assert result['retry_limit_reached'] is True
    assert 'draft paths and validation errors' in result['message']
    assert result['draft_id'] == 'demo'
    assert result['draft_metadata_path'] == 'skills/drafts/demo.json'
    hidden = json.loads(agent.messages[-1]['content'])
    assert hidden['retry_limit_reached'] is True
    assert hidden['validation_errors'] == [{'field': 'inputs', 'message': 'bad input'}]
    assert hidden['repair_suggestions'] == [{'field': 'inputs', 'replace': 'file_path', 'with': 'path'}]
