from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.skills import (
    ExecutionGuidance,
    ForbiddenToolCall,
    RecommendedToolCall,
    ResolvedTaskType,
)


def test_execution_guidance_serializes_valid_payload():
    guidance = ExecutionGuidance(
        resolved_task_type=ResolvedTaskType.SPECIFIC_FUNCTION_EXPLANATION,
        recommended_tool_calls=[
            RecommendedToolCall(
                tool='list_code_symbols',
                arguments={'path': 'auth.py'},
                reason='Discover available symbols before selecting one.',
            ),
            {
                'tool': 'explain_function_for_model',
                'arguments': {'path': 'auth.py', 'symbol': 'login'},
                'reason': 'Explain only the explicitly requested symbol.',
            },
        ],
        allowed_tools=['list_code_symbols', 'explain_function_for_model'],
        forbidden_tool_calls=[
            ForbiddenToolCall(
                tool='summarize_code_file',
                reason='A specific symbol was requested.',
            )
        ],
        procedure_overrides=['Call list_code_symbols before explaining a function.'],
    )

    assert guidance.to_payload() == {
        'resolved_task_type': 'specific_function_explanation',
        'recommended_tool_calls': [
            {
                'tool': 'list_code_symbols',
                'arguments': {'path': 'auth.py'},
                'reason': 'Discover available symbols before selecting one.',
            },
            {
                'tool': 'explain_function_for_model',
                'arguments': {'path': 'auth.py', 'symbol': 'login'},
                'reason': 'Explain only the explicitly requested symbol.',
            },
        ],
        'allowed_tools': ['list_code_symbols', 'explain_function_for_model'],
        'forbidden_tool_calls': [
            {
                'tool': 'summarize_code_file',
                'reason': 'A specific symbol was requested.',
            }
        ],
        'procedure_overrides': ['Call list_code_symbols before explaining a function.'],
    }


def test_execution_guidance_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ExecutionGuidance(
            resolved_task_type='generic_skill_procedure',
            unexpected='value',
        )


def test_recommended_tool_call_rejects_empty_tool_name():
    with pytest.raises(ValidationError):
        RecommendedToolCall(tool='')


def test_forbidden_tool_call_rejects_empty_tool_name():
    with pytest.raises(ValidationError):
        ForbiddenToolCall(tool='', reason='Not allowed for this workflow.')


def test_forbidden_tool_call_rejects_empty_required_reason():
    with pytest.raises(ValidationError):
        ForbiddenToolCall(tool='read_file', reason='')


def test_execution_guidance_rejects_allowed_forbidden_overlap():
    with pytest.raises(ValidationError, match='tools cannot be both allowed and forbidden'):
        ExecutionGuidance(
            resolved_task_type='whole_file_code_overview',
            allowed_tools=['summarize_code_file'],
            forbidden_tool_calls=[
                {
                    'tool': 'summarize_code_file',
                    'reason': 'Conflicting policy.',
                }
            ],
        )


def test_execution_guidance_rejects_non_allowed_recommended_tool():
    with pytest.raises(ValidationError, match='recommended tools must be allowed'):
        ExecutionGuidance(
            resolved_task_type='owasp_security_review',
            allowed_tools=['search_owasp_reference'],
            recommended_tool_calls=[
                {
                    'tool': 'discover_review_targets',
                    'arguments': {'root': 'app.py'},
                }
            ],
        )


def test_execution_guidance_allows_repeated_recommendations_with_different_arguments():
    guidance = ExecutionGuidance(
        resolved_task_type='owasp_security_review',
        allowed_tools=['search_owasp_reference'],
        recommended_tool_calls=[
            {
                'tool': 'search_owasp_reference',
                'arguments': {'query': 'injection'},
            },
            {
                'tool': 'search_owasp_reference',
                'arguments': {'query': 'authentication'},
            },
        ],
    )

    assert guidance.to_payload()['recommended_tool_calls'] == [
        {
            'tool': 'search_owasp_reference',
            'arguments': {'query': 'injection'},
        },
        {
            'tool': 'search_owasp_reference',
            'arguments': {'query': 'authentication'},
        },
    ]


def test_execution_guidance_rejects_unknown_resolved_task_type():
    with pytest.raises(ValidationError):
        ExecutionGuidance(resolved_task_type='unknown_task_type')
