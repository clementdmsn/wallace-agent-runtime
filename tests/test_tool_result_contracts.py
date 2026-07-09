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
    OwaspCorpusError,
    OwaspReferenceMatch,
    OwaspReferenceResult,
    ReviewTarget,
    ReviewTargetResult,
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


def test_owasp_reference_result_serializes_corpus_validation_errors():
    error = OwaspCorpusError(line=3, error='missing required field(s): text')

    result = OwaspReferenceResult(
        status=ResultStatus.ERROR,
        path='knowledge_base/owasp/corpus.jsonl',
        record_count=1,
        errors=[error],
        content_hash='abc123',
    )

    assert result.to_payload() == {
        'status': 'error',
        'path': 'knowledge_base/owasp/corpus.jsonl',
        'record_count': 1,
        'errors': [
            {
                'line': 3,
                'error': 'missing required field(s): text',
            }
        ],
        'content_hash': 'abc123',
        'matches': [],
    }


def test_owasp_reference_result_serializes_search_matches():
    match = OwaspReferenceMatch(
        row_id=0,
        distance=0.5,
        source='ASVS',
        version='5.0.0',
        reference_id='v5.0.0-V1.2.4',
        title='Injection Prevention',
        category='Encoding and Sanitization',
        url='https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release',
        text='Verify that database queries use parameterized queries to prevent injection.',
    )

    result = OwaspReferenceResult(
        status=ResultStatus.OK,
        query='sql injection query',
        count=1,
        matches=[match],
    )

    assert result.to_payload() == {
        'status': 'ok',
        'query': 'sql injection query',
        'count': 1,
        'errors': [],
        'matches': [
            {
                'row_id': 0,
                'distance': 0.5,
                'source': 'ASVS',
                'version': '5.0.0',
                'reference_id': 'v5.0.0-V1.2.4',
                'title': 'Injection Prevention',
                'category': 'Encoding and Sanitization',
                'url': 'https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release',
                'text': 'Verify that database queries use parameterized queries to prevent injection.',
            }
        ],
    }


def test_owasp_reference_result_serializes_rebuild_payload():
    result = OwaspReferenceResult(
        status=ResultStatus.OK,
        index_path='knowledge_base/owasp/indexes/owasp.faiss',
        map_path='knowledge_base/owasp/indexes/owasp.map.json',
        record_count=2,
        total_rows=2,
        message='OWASP reference index rebuilt',
    )

    assert result.to_payload() == {
        'status': 'ok',
        'message': 'OWASP reference index rebuilt',
        'record_count': 2,
        'errors': [],
        'index_path': 'knowledge_base/owasp/indexes/owasp.faiss',
        'map_path': 'knowledge_base/owasp/indexes/owasp.map.json',
        'total_rows': 2,
        'matches': [],
    }


def test_review_target_result_serializes_targets():
    target = ReviewTarget(
        path='src/app.py',
        kind='file',
        suffix='.py',
        size_bytes=42,
    )

    result = ReviewTargetResult(
        status=ResultStatus.OK,
        root='.',
        targets=[target],
        count=1,
        total_candidates=3,
        truncated=True,
        max_files=1,
        skipped_directories=['.git', 'node_modules'],
    )

    assert result.to_payload() == {
        'status': 'ok',
        'root': '.',
        'targets': [
            {
                'path': 'src/app.py',
                'kind': 'file',
                'suffix': '.py',
                'size_bytes': 42,
            }
        ],
        'count': 1,
        'total_candidates': 3,
        'truncated': True,
        'max_files': 1,
        'skipped_directories': ['.git', 'node_modules'],
    }


def test_review_target_result_allows_error_without_root():
    result = ReviewTargetResult(status=ResultStatus.ERROR, error='root must be a non-empty string')

    assert result.to_payload() == {
        'status': 'error',
        'error': 'root must be a non-empty string',
        'targets': [],
        'skipped_directories': [],
    }
