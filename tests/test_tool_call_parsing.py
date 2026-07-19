from __future__ import annotations

import pytest

from agent.tool_call_parsing import ParsedToolCall, parse_tool_args, parse_tool_call, reject_json_constant


def test_parse_tool_call_extracts_function_payload():
    parsed = parse_tool_call({
        'id': 'call-1',
        'function': {
            'name': 'read_file',
            'arguments': '{"path": "README.md"}',
        },
    })

    assert parsed == ParsedToolCall(
        call_id='call-1',
        name='read_file',
        raw_args='{"path": "README.md"}',
    )


def test_parse_tool_call_defaults_missing_fields():
    parsed = parse_tool_call({})

    assert parsed == ParsedToolCall(call_id='', name='', raw_args='{}')


def test_parse_tool_args_returns_decoded_object():
    args, error = parse_tool_args('{"path": "README.md"}')

    assert args == {'path': 'README.md'}
    assert error is None


@pytest.mark.parametrize('raw_args', ['{bad json', '[]', 'NaN', 'Infinity', '-Infinity'])
def test_parse_tool_args_reports_invalid_arguments(raw_args: str):
    args, error = parse_tool_args(raw_args)

    assert args is None
    assert error is not None
    assert error['status'] == 'error'
    assert 'invalid call arguments' in error['error']


def test_reject_json_constant_rejects_non_finite_values():
    with pytest.raises(ValueError, match='invalid JSON constant: NaN'):
        reject_json_constant('NaN')
