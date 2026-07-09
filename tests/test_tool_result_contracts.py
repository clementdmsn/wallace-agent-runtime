from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.base import ResultStatus
from contracts.tool_results import (
    CodeSymbol,
    CurlResult,
    FunctionExplanationContent,
    GenericToolResult,
    ListCodeSymbolsResult,
    ExplainFunctionResult,
    SkillIndexMatch,
    SkillIndexResult,
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


def test_curl_result_serializes_success_payload():
    result = CurlResult(
        status=ResultStatus.OK,
        url='https://docs.python.org/3/',
        final_url='https://docs.python.org/3/',
        title='Python Docs',
        content='Library\nUseful text.',
        truncated=False,
    )

    assert result.to_payload() == {
        'status': 'ok',
        'url': 'https://docs.python.org/3/',
        'final_url': 'https://docs.python.org/3/',
        'title': 'Python Docs',
        'content': 'Library\nUseful text.',
        'truncated': False,
    }


def test_curl_result_serializes_approval_payload():
    result = CurlResult(
        status=ResultStatus.APPROVAL_REQUIRED,
        url='https://docs.python.org/3/',
        domain='docs.python.org',
        approval_id='curl:docs.python.org:123',
    )

    assert result.to_payload() == {
        'status': 'approval_required',
        'url': 'https://docs.python.org/3/',
        'domain': 'docs.python.org',
        'approval_id': 'curl:docs.python.org:123',
    }


def test_skill_index_result_serializes_search_matches():
    match = SkillIndexMatch(
        row_id=3,
        distance=0.25,
        skill_name='demo_skill',
        source_path='skill_catalog/metadatas/demo.json',
        chunk_index=1,
        text='summary: Demo',
    )

    result = SkillIndexResult(
        status=ResultStatus.OK,
        query='demo',
        count=1,
        matches=[match],
    )

    assert result.to_payload() == {
        'status': 'ok',
        'query': 'demo',
        'count': 1,
        'matches': [
            {
                'row_id': 3,
                'distance': 0.25,
                'skill_name': 'demo_skill',
                'source_path': 'skill_catalog/metadatas/demo.json',
                'chunk_index': 1,
                'text': 'summary: Demo',
            }
        ],
    }


def test_skill_index_result_serializes_index_write_payload():
    result = SkillIndexResult(
        status=ResultStatus.OK,
        path='skill_catalog/metadatas/demo.json',
        index_path='skills/indexes/skills.faiss',
        map_path='skills/indexes/skills.map.json',
        created=True,
        rows_added=2,
        total_rows=2,
        message='skill metadata added to FAISS index',
    )

    assert result.to_payload() == {
        'status': 'ok',
        'message': 'skill metadata added to FAISS index',
        'path': 'skill_catalog/metadatas/demo.json',
        'index_path': 'skills/indexes/skills.faiss',
        'map_path': 'skills/indexes/skills.map.json',
        'created': True,
        'rows_added': 2,
        'total_rows': 2,
        'matches': [],
    }
