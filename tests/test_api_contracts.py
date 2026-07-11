from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.api import ApiErrorResponse, ApiOkResponse, RuntimeStateResponse, VisibleMessage


def test_visible_message_serializes_known_fields():
    message = VisibleMessage(role='assistant', content='hello')

    assert message.to_payload() == {
        'role': 'assistant',
        'content': 'hello',
    }


def test_visible_message_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        VisibleMessage(role='assistant', content='hello', unexpected='value')


def test_visible_message_rejects_non_exposed_role():
    with pytest.raises(ValidationError):
        VisibleMessage(role='system', content='hidden')


def test_runtime_state_response_uses_safe_defaults():
    response = RuntimeStateResponse(is_generating=False)

    assert response.messages == []
    assert response.tool_events == []
    assert response.runtime_metrics == {}
    assert response.active_skill_policy == {}
    assert response.to_payload() == {
        'messages': [],
        'tool_events': [],
        'runtime_metrics': {},
        'active_skill_name': None,
        'active_skill_policy': {},
        'is_generating': False,
        'last_error': '',
        'pending_approval': None,
    }


def test_runtime_state_response_serializes_current_state_shape():
    response = RuntimeStateResponse(
        messages=[
            {'role': 'user', 'content': 'hello'},
            VisibleMessage(role='assistant', content='hi'),
        ],
        tool_events=[
            {
                'kind': 'tool',
                'tool': 'read_file',
                'result': {'status': 'ok'},
            },
            {
                'kind': 'skill_selection',
                'status': 'ok',
                'skill_name': 'owasp_security_review',
                'selection': {'forced': True},
            },
            {
                'kind': 'skill_policy',
                'status': 'error',
                'error': 'missing required reference search',
            }
        ],
        runtime_metrics={'last_request': {'model': 'demo'}},
        active_skill_name='owasp_security_review',
        active_skill_policy={'allowed_tools': ['search_owasp_reference']},
        is_generating=True,
        last_error='Waiting for user approval.',
        pending_approval={
            'tool': 'curl_url',
            'call_id': 'call-1',
            'args': {'url': 'https://docs.python.org/3/'},
            'approval_id': 'curl:docs.python.org:123',
            'domain': 'docs.python.org',
            'url': 'https://docs.python.org/3/',
        },
    )

    assert response.to_payload() == {
        'messages': [
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'hi'},
        ],
        'tool_events': [
            {
                'id': '',
                'kind': 'tool',
                'args': {},
                'tool': 'read_file',
                'result': {'status': 'ok'},
            },
            {
                'kind': 'skill_selection',
                'status': 'ok',
                'skill_name': 'owasp_security_review',
                'selection': {'forced': True},
            },
            {
                'kind': 'skill_policy',
                'status': 'error',
                'error': 'missing required reference search',
            }
        ],
        'runtime_metrics': {'last_request': {'model': 'demo'}},
        'active_skill_name': 'owasp_security_review',
        'active_skill_policy': {'allowed_tools': ['search_owasp_reference']},
        'is_generating': True,
        'last_error': 'Waiting for user approval.',
        'pending_approval': {
            'tool': 'curl_url',
            'call_id': 'call-1',
            'args': {'url': 'https://docs.python.org/3/'},
            'approval_id': 'curl:docs.python.org:123',
            'domain': 'docs.python.org',
            'url': 'https://docs.python.org/3/',
        },
    }


def test_runtime_state_response_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RuntimeStateResponse(is_generating=False, unexpected='value')


def test_runtime_state_response_rejects_unknown_event_kind():
    with pytest.raises(ValidationError):
        RuntimeStateResponse(
            is_generating=False,
            tool_events=[{'kind': 'unknown', 'status': 'ok'}],
        )


def test_runtime_state_response_rejects_malformed_event_status():
    with pytest.raises(ValidationError):
        RuntimeStateResponse(
            is_generating=False,
            tool_events=[{'kind': 'skill_policy', 'status': 'ok'}],
        )


def test_runtime_state_response_defaults_are_not_shared():
    first = RuntimeStateResponse(is_generating=False)
    second = RuntimeStateResponse(is_generating=False)

    first.messages.append(VisibleMessage(role='user', content='hello'))
    first.tool_events.append({'kind': 'tool'})
    first.runtime_metrics['request_count'] = 1
    first.active_skill_policy['allowed_tools'] = ['read_file']

    assert second.messages == []
    assert second.tool_events == []
    assert second.runtime_metrics == {}
    assert second.active_skill_policy == {}


def test_api_ok_response_serializes_success_flag():
    assert ApiOkResponse().to_payload() == {'ok': True}


def test_api_error_response_serializes_error_message():
    response = ApiErrorResponse(error='Empty message')

    assert response.to_payload() == {
        'ok': False,
        'error': 'Empty message',
    }
