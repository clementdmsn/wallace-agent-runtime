from __future__ import annotations

import threading

from agent import registered_tool_execution
from tools.tool_registry import Tool


class FakeAgent:
    def __init__(self):
        self.lock = threading.RLock()
        self.active_skill_name = None
        self.active_skill_policy = {}
        self.skill_creation_failures = 0
        self.skill_tool_call_index = 0
        self.verified_symbols_by_path = {}
        self.owasp_reference_search_count = 0


def test_run_tool_returns_parse_errors_without_executing_tool(monkeypatch):
    called = []
    monkeypatch.setitem(
        registered_tool_execution.TOOLS,
        'fake_tool',
        Tool('fake_tool', lambda value: called.append(value) or {'status': 'ok'}),
    )

    execution = registered_tool_execution.run_tool(FakeAgent(), 'fake_tool', '{"value": NaN}')

    assert execution.kind == 'tool'
    assert execution.args == {}
    assert execution.result['status'] == 'error'
    assert 'invalid JSON constant: NaN' in execution.result['error']
    assert called == []


def test_run_tool_reports_unknown_tools():
    execution = registered_tool_execution.run_tool(FakeAgent(), 'missing_tool', '{}')

    assert execution.kind == 'tool'
    assert execution.args == {}
    assert execution.result == {
        'status': 'error',
        'error': 'unknown tool: missing_tool',
        'message': 'Only registered tools are executable.',
    }


def test_execute_registered_tool_runs_tool_and_tracks_skill_success(monkeypatch):
    agent = FakeAgent()
    agent.active_skill_name = 'demo_skill'
    recorded_events = []
    monkeypatch.setattr(
        registered_tool_execution,
        'record_skill_event',
        lambda skill_name, event: recorded_events.append((skill_name, event)),
    )
    monkeypatch.setitem(
        registered_tool_execution.TOOLS,
        'fake_tool',
        Tool('fake_tool', lambda path: {'status': 'ok', 'path': path}),
    )

    result = registered_tool_execution.execute_registered_tool(agent, 'fake_tool', {'path': 'README.md'})

    assert result == {'status': 'ok', 'path': 'README.md'}
    assert agent.skill_tool_call_index == 1
    assert recorded_events == [('demo_skill', 'used'), ('demo_skill', 'success')]


def test_skill_authoring_retry_policy_marks_third_validation_failure():
    agent = FakeAgent()
    result = {
        'status': 'error',
        'error': 'json_payload failed skill quality validation',
    }

    assert registered_tool_execution.apply_skill_authoring_retry_policy(agent, 'create_skill', result) == result
    assert registered_tool_execution.apply_skill_authoring_retry_policy(agent, 'create_skill', result) == result
    final_result = registered_tool_execution.apply_skill_authoring_retry_policy(agent, 'create_skill', result)

    assert final_result['retry_limit_reached'] is True
    assert 'draft paths and validation errors' in final_result['message']


def test_validate_registered_tool_result_leaves_non_curl_results_unchanged():
    result = {'status': 'ok'}

    assert registered_tool_execution.validate_registered_tool_result('read_file', result) is result
