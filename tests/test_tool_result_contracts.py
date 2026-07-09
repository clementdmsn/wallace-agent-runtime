from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.base import ResultStatus
from contracts.tool_results import (
    CodeSymbol,
    FunctionExplanationContent,
    GenericToolResult,
    ListCodeSymbolsResult,
    ExplainFunctionResult,
    ToolResult,
)


def test_tool_result_accepts_shared_status_values():
    result = ToolResult(status='ok', message='done')

    assert result.status == 'ok'
    assert result.to_payload() == {
        'status': 'ok',
        'message': 'done',
    }


def test_tool_result_serializes_status_enum_values():
    result = ToolResult(status=ResultStatus.APPROVAL_REQUIRED)

    assert result.to_payload() == {'status': 'approval_required'}


def test_tool_result_rejects_unknown_status():
    with pytest.raises(ValidationError):
        ToolResult(status='pending')


def test_generic_tool_result_excludes_empty_optional_fields():
    result = GenericToolResult(
        status=ResultStatus.OK,
        path='demo.txt',
        content='hello',
        truncated=False,
    )

    assert result.to_payload() == {
        'status': 'ok',
        'path': 'demo.txt',
        'content': 'hello',
        'truncated': False,
    }


def test_generic_tool_result_supports_line_numbered_payloads():
    result = GenericToolResult(
        status=ResultStatus.OK,
        path='app.py',
        content='1: print("hello")\n',
        truncated=False,
        line_numbered=True,
    )

    assert result.to_payload() == {
        'status': 'ok',
        'path': 'app.py',
        'content': '1: print("hello")\n',
        'truncated': False,
        'line_numbered': True,
    }


def test_generic_tool_result_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        GenericToolResult(status='ok', unexpected='value')


def test_list_code_symbols_result_serializes_nested_symbols():
    symbol = CodeSymbol(
        name='helper',
        qualified_name='helper',
        kind='function',
        lines=[1, 3],
    )

    result = ListCodeSymbolsResult(
        status=ResultStatus.OK,
        path='demo.py',
        symbols=[symbol],
        content=[symbol],
    )

    assert result.to_payload() == {
        'status': 'ok',
        'path': 'demo.py',
        'symbols': [
            {
                'name': 'helper',
                'qualified_name': 'helper',
                'kind': 'function',
                'lines': [1, 3],
            }
        ],
        'content': [
            {
                'name': 'helper',
                'qualified_name': 'helper',
                'kind': 'function',
                'lines': [1, 3],
            }
        ],
    }


def test_function_explanation_result_serializes_content_model():
    content = FunctionExplanationContent(
        qualified_name='Demo.method',
        kind='method',
        lines=[2, 4],
        docstring=None,
        params=['self', 'value'],
        calls=['helper'],
        writes=['self.value'],
        effects=['state_mutation'],
        summary='calls helper; writes self.value',
    )

    result = ExplainFunctionResult(
        status=ResultStatus.OK,
        path='demo.py',
        symbol='Demo.method',
        content=content,
    )

    assert result.to_payload() == {
        'status': 'ok',
        'path': 'demo.py',
        'symbol': 'Demo.method',
        'content': {
            'qualified_name': 'Demo.method',
            'kind': 'method',
            'lines': [2, 4],
            'params': ['self', 'value'],
            'decorators': [],
            'calls': ['helper'],
            'returns': [],
            'raises': [],
            'writes': ['self.value'],
            'reads': [],
            'instance_attributes': [],
            'nested_symbols': [],
            'effects': ['state_mutation'],
            'summary': 'calls helper; writes self.value',
        },
    }


def test_explain_function_result_allows_ambiguous_symbol_content():
    result = ExplainFunctionResult(
        status=ResultStatus.ERROR,
        path='demo.py',
        symbol='duplicate',
        error='symbol is ambiguous',
        content=['First.duplicate', 'Second.duplicate'],
    )

    assert result.to_payload() == {
        'status': 'error',
        'error': 'symbol is ambiguous',
        'path': 'demo.py',
        'symbol': 'duplicate',
        'content': ['First.duplicate', 'Second.duplicate'],
    }
