from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.events import PendingApproval, ToolEvent


def test_tool_event_requires_kind():
    with pytest.raises(ValidationError):
        ToolEvent()


def test_tool_event_uses_safe_defaults():
    event = ToolEvent(kind='tool')

    assert event.id == ''
    assert event.args == {}
    assert event.to_payload() == {
        'id': '',
        'kind': 'tool',
        'args': {},
    }


def test_tool_event_serializes_known_fields():
    event = ToolEvent(
        id='call-1',
        kind='tool',
        tool='read_file',
        args={'path': 'notes.txt'},
        result={'status': 'ok', 'path': 'notes.txt'},
        status='ok',
        message='file read',
    )

    assert event.to_payload() == {
        'id': 'call-1',
        'kind': 'tool',
        'args': {'path': 'notes.txt'},
        'result': {'status': 'ok', 'path': 'notes.txt'},
        'tool': 'read_file',
        'status': 'ok',
        'message': 'file read',
    }


def test_tool_event_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ToolEvent(kind='tool', unexpected='value')


def test_tool_event_args_default_is_not_shared():
    first = ToolEvent(kind='tool')
    second = ToolEvent(kind='tool')

    first.args['path'] = 'notes.txt'

    assert second.args == {}


def test_pending_approval_requires_core_fields():
    with pytest.raises(ValidationError):
        PendingApproval(tool='curl_url', approval_id='curl:docs.python.org:123')


def test_pending_approval_uses_safe_defaults():
    approval = PendingApproval(
        tool='curl_url',
        approval_id='curl:docs.python.org:123',
        domain='docs.python.org',
    )

    assert approval.call_id == ''
    assert approval.args == {}
    assert approval.to_payload() == {
        'tool': 'curl_url',
        'call_id': '',
        'args': {},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
    }


def test_pending_approval_serializes_known_fields():
    approval = PendingApproval(
        tool='curl_url',
        call_id='call-1',
        args={'url': 'https://docs.python.org/3/'},
        approval_id='curl:docs.python.org:123',
        domain='docs.python.org',
        url='https://docs.python.org/3/',
    )

    assert approval.to_payload() == {
        'tool': 'curl_url',
        'call_id': 'call-1',
        'args': {'url': 'https://docs.python.org/3/'},
        'approval_id': 'curl:docs.python.org:123',
        'domain': 'docs.python.org',
        'url': 'https://docs.python.org/3/',
    }


def test_pending_approval_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        PendingApproval(
            tool='curl_url',
            approval_id='curl:docs.python.org:123',
            domain='docs.python.org',
            unexpected='value',
        )


def test_pending_approval_args_default_is_not_shared():
    first = PendingApproval(
        tool='curl_url',
        approval_id='curl:docs.python.org:123',
        domain='docs.python.org',
    )
    second = PendingApproval(
        tool='curl_url',
        approval_id='curl:docs.python.org:456',
        domain='docs.python.org',
    )

    first.args['url'] = 'https://docs.python.org/3/'

    assert second.args == {}
