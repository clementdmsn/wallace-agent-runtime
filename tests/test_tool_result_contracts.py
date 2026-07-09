from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.base import ResultStatus
from contracts.tool_results import GenericToolResult, ToolResult


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


def test_generic_tool_result_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        GenericToolResult(status='ok', unexpected='value')
