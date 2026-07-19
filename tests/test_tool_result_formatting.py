from __future__ import annotations

import json

from agent.tool_call_parsing import ParsedToolCall
from agent.tool_result_formatting import (
    ToolExecutionResult,
    hidden_tool_message,
    result_payload,
    result_status,
    tool_event,
)


def parsed_tool_call() -> ParsedToolCall:
    return ParsedToolCall(
        call_id='call-1',
        name='read_file',
        raw_args='{"path": "README.md"}',
    )


def test_result_payload_formats_non_dict_results():
    assert result_payload('echo', 'hello', 'tool') == {
        'tool': 'echo',
        'status': 'ok',
        'text': 'hello',
    }


def test_result_payload_keeps_allowed_result_fields():
    payload = result_payload(
        'read_file',
        {
            'status': 'ok',
            'path': 'README.md',
            'content': 'hello',
            'ignored': 'value',
        },
        'tool',
    )

    assert payload == {
        'tool': 'read_file',
        'status': 'ok',
        'path': 'README.md',
        'content': 'hello',
    }


def test_hidden_tool_message_serializes_result_payload():
    execution = ToolExecutionResult(
        kind='tool',
        args={'path': 'README.md'},
        result={'status': 'ok', 'path': 'README.md', 'content': 'hello'},
    )

    message = hidden_tool_message(parsed_tool_call(), execution)

    assert message['role'] == 'tool'
    assert message['tool_call_id'] == 'call-1'
    assert json.loads(message['content']) == {
        'tool': 'read_file',
        'status': 'ok',
        'path': 'README.md',
        'content': 'hello',
    }


def test_hidden_tool_message_uses_fallback_tool_call_id():
    parsed = ParsedToolCall(call_id='', name='read_file', raw_args='{}')
    execution = ToolExecutionResult(kind='tool', args={}, result={'status': 'ok'})

    message = hidden_tool_message(parsed, execution)

    assert message['tool_call_id'] == 'tool:read_file'


def test_tool_event_serializes_execution_result():
    execution = ToolExecutionResult(
        kind='tool',
        args={'path': 'README.md'},
        result={'status': 'ok', 'path': 'README.md'},
    )

    assert tool_event(parsed_tool_call(), execution) == {
        'id': 'call-1',
        'kind': 'tool',
        'tool': 'read_file',
        'args': {'path': 'README.md'},
        'result': {'status': 'ok', 'path': 'README.md'},
    }


def test_result_status_reads_dict_status():
    assert result_status({'status': 'approval_required'}) == 'approval_required'


def test_result_status_defaults_non_dict_results_to_ok():
    assert result_status('plain text') == 'ok'
