from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.skills import (
    ExecutionGuidance,
    ForbiddenToolCall,
    RecommendedToolCall,
    RejectedSkillCandidate,
    RequestedSkillResult,
    ResolvedTaskType,
    SkillCandidate,
    SkillSelectionResult,
    SkillValidation,
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


def test_skill_validation_serializes_valid_payload():
    validation = SkillValidation(
        valid=True,
        score=8.5,
        reasons=['tag_match', 'filetype_match'],
        intent={
            'text': 'explain app.py',
            'tokens': ['app.py', 'explain', 'python'],
            'args': {'path': 'app.py'},
            'action': 'summarize',
            'filetype': 'py',
            'domain': 'code',
            'speech_act': 'command',
        },
    )

    assert validation.to_payload() == {
        'valid': True,
        'score': 8.5,
        'reasons': ['tag_match', 'filetype_match'],
        'intent': {
            'text': 'explain app.py',
            'tokens': ['app.py', 'explain', 'python'],
            'args': {'path': 'app.py'},
            'action': 'summarize',
            'filetype': 'py',
            'domain': 'code',
            'speech_act': 'command',
        },
    }


def test_skill_validation_uses_safe_reason_defaults():
    first = SkillValidation(valid=True)
    second = SkillValidation(valid=False)

    first.reasons.append('matched')

    assert second.reasons == []
    assert second.to_payload() == {
        'valid': False,
        'reasons': [],
    }


def test_skill_validation_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        SkillValidation(valid=True, unexpected='value')


def test_skill_candidate_serializes_ranking_metadata():
    candidate = SkillCandidate(
        skill_name='code_explainer',
        score=9.25,
        distance=0.12,
        priority=5,
        forced=True,
    )

    assert candidate.to_payload() == {
        'skill_name': 'code_explainer',
        'score': 9.25,
        'distance': 0.12,
        'priority': 5,
        'forced': True,
    }


def test_skill_candidate_uses_default_forced_flag():
    candidate = SkillCandidate(skill_name='code_explainer')

    assert candidate.to_payload() == {
        'skill_name': 'code_explainer',
        'forced': False,
    }


def test_skill_candidate_rejects_empty_skill_name():
    with pytest.raises(ValidationError):
        SkillCandidate(skill_name='')


def test_skill_candidate_rejects_negative_distance():
    with pytest.raises(ValidationError):
        SkillCandidate(skill_name='code_explainer', distance=-0.1)


def test_skill_candidate_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        SkillCandidate(skill_name='code_explainer', unexpected='value')


def test_rejected_skill_candidate_serializes_rejection_reason():
    candidate = RejectedSkillCandidate(
        skill_name='owasp_security_review',
        reason='missing required path',
        score=4.0,
        distance=1.5,
    )

    assert candidate.to_payload() == {
        'skill_name': 'owasp_security_review',
        'rejection_reason': 'missing required path',
        'score': 4.0,
        'distance': 1.5,
    }


def test_rejected_skill_candidate_accepts_compatibility_rejection_reason():
    candidate = RejectedSkillCandidate(
        skill_name='owasp_security_review',
        rejection_reason='missing required path',
    )

    assert candidate.reason == 'missing required path'
    assert candidate.to_payload() == {
        'skill_name': 'owasp_security_review',
        'rejection_reason': 'missing required path',
    }


def test_rejected_skill_candidate_rejects_empty_reason():
    with pytest.raises(ValidationError):
        RejectedSkillCandidate(skill_name='code_explainer', reason='')


def test_rejected_skill_candidate_rejects_negative_distance():
    with pytest.raises(ValidationError):
        RejectedSkillCandidate(
            skill_name='code_explainer',
            reason='below threshold',
            distance=-1,
        )


def test_skill_selection_result_serializes_nested_selection_payload():
    result = SkillSelectionResult(
        status='ok',
        skill_name='code_explainer',
        selection_reason='best candidate above threshold',
        message='Selected code_explainer.',
        validation={
            'valid': True,
            'score': 9.0,
            'reasons': ['tag_match'],
            'intent': {
                'text': 'explain app.py',
                'tokens': ['app.py', 'explain', 'python'],
                'args': {'path': 'app.py'},
                'action': 'summarize',
                'filetype': 'py',
                'domain': 'code',
                'speech_act': 'command',
            },
        },
        distance=0.25,
        forced=True,
        best_candidate={
            'skill_name': 'code_explainer',
            'score': 9.0,
            'distance': 0.25,
            'priority': 3,
        },
        candidates=[
            SkillCandidate(skill_name='code_explainer', score=9.0, distance=0.25),
            {
                'skill_name': 'owasp_security_review',
                'score': 4.0,
                'distance': 1.2,
            },
        ],
        rejected_candidates=[
            {
                'skill_name': 'create_new_skill',
                'rejection_reason': 'below threshold',
                'score': 2.0,
                'distance': 2.2,
            }
        ],
    )

    assert result.to_payload() == {
        'status': 'ok',
        'skill_name': 'code_explainer',
        'selection_reason': 'best candidate above threshold',
        'message': 'Selected code_explainer.',
        'validation': {
            'valid': True,
            'score': 9.0,
            'reasons': ['tag_match'],
            'intent': {
                'text': 'explain app.py',
                'tokens': ['app.py', 'explain', 'python'],
                'args': {'path': 'app.py'},
                'action': 'summarize',
                'filetype': 'py',
                'domain': 'code',
                'speech_act': 'command',
            },
        },
        'distance': 0.25,
        'forced': True,
        'best_candidate': {
            'skill_name': 'code_explainer',
            'score': 9.0,
            'distance': 0.25,
            'priority': 3,
            'forced': False,
        },
        'candidates': [
            {
                'skill_name': 'code_explainer',
                'score': 9.0,
                'distance': 0.25,
                'forced': False,
            },
            {
                'skill_name': 'owasp_security_review',
                'score': 4.0,
                'distance': 1.2,
                'forced': False,
            },
        ],
        'rejected_candidates': [
            {
                'skill_name': 'create_new_skill',
                'rejection_reason': 'below threshold',
                'score': 2.0,
                'distance': 2.2,
            }
        ],
    }


def test_skill_selection_result_uses_safe_defaults():
    result = SkillSelectionResult(status='error')

    assert result.to_payload() == {
        'status': 'error',
        'forced': False,
        'candidates': [],
        'rejected_candidates': [],
    }


def test_skill_selection_result_default_lists_are_not_shared():
    first = SkillSelectionResult(status='ok')
    second = SkillSelectionResult(status='ok')

    first.candidates.append(SkillCandidate(skill_name='code_explainer'))
    first.rejected_candidates.append(
        RejectedSkillCandidate(skill_name='owasp_security_review', reason='below threshold')
    )

    assert second.candidates == []
    assert second.rejected_candidates == []


def test_skill_selection_result_rejects_unknown_status():
    with pytest.raises(ValidationError):
        SkillSelectionResult(status='pending')


def test_skill_selection_result_rejects_negative_distance():
    with pytest.raises(ValidationError):
        SkillSelectionResult(status='ok', distance=-0.01)


def test_skill_selection_result_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        SkillSelectionResult(status='ok', unexpected='value')


def test_requested_skill_result_serializes_flattened_guidance_payload():
    result = RequestedSkillResult(
        status='ok',
        skill_name='code_explainer',
        description='Explain code.',
        procedure='Read the file and summarize the target.',
        metadata_path='skills/metadatas/code_explainer.json',
        procedure_path='skills/procedures/code_explainer.md',
        tools_required=['read_file'],
        preconditions=['A path is available.'],
        when_to_use=['Use for code explanation.'],
        when_not_to_use=['Do not use for security audits.'],
        exclusions=['security_review'],
        arguments={'path': 'app.py'},
        selection={
            'status': 'ok',
            'skill_name': 'code_explainer',
            'validation': {
                'valid': True,
                'score': 9.0,
                'reasons': ['tag_match'],
                'intent': {
                    'text': 'explain app.py',
                    'tokens': ['app.py', 'explain', 'python'],
                    'args': {'path': 'app.py'},
                    'action': 'summarize',
                    'filetype': 'py',
                    'domain': 'code',
                    'speech_act': 'command',
                },
            },
            'candidates': [{'skill_name': 'code_explainer', 'score': 9.0}],
        },
        guidance={
            'resolved_task_type': 'whole_file_code_overview',
            'recommended_tool_calls': [
                {
                    'tool': 'read_file',
                    'arguments': {'path': 'app.py'},
                    'reason': 'Read the target file first.',
                }
            ],
            'allowed_tools': ['read_file'],
            'forbidden_tool_calls': [
                {
                    'tool': 'search_owasp_reference',
                    'reason': 'A security audit was not requested.',
                }
            ],
            'procedure_overrides': ['Read the file before answering.'],
        },
        message='Follow the selected skill procedure.',
    )

    assert result.to_payload() == {
        'status': 'ok',
        'skill_name': 'code_explainer',
        'arguments': {'path': 'app.py'},
        'selection': {
            'status': 'ok',
            'skill_name': 'code_explainer',
            'validation': {
                'valid': True,
                'score': 9.0,
                'reasons': ['tag_match'],
                'intent': {
                    'text': 'explain app.py',
                    'tokens': ['app.py', 'explain', 'python'],
                    'args': {'path': 'app.py'},
                    'action': 'summarize',
                    'filetype': 'py',
                    'domain': 'code',
                    'speech_act': 'command',
                },
            },
            'forced': False,
            'candidates': [{'skill_name': 'code_explainer', 'score': 9.0, 'forced': False}],
            'rejected_candidates': [],
        },
        'description': 'Explain code.',
        'procedure': 'Read the file and summarize the target.',
        'metadata_path': 'skills/metadatas/code_explainer.json',
        'procedure_path': 'skills/procedures/code_explainer.md',
        'tools_required': ['read_file'],
        'preconditions': ['A path is available.'],
        'when_to_use': ['Use for code explanation.'],
        'when_not_to_use': ['Do not use for security audits.'],
        'exclusions': ['security_review'],
        'message': 'Follow the selected skill procedure.',
        'resolved_task_type': 'whole_file_code_overview',
        'recommended_tool_calls': [
            {
                'tool': 'read_file',
                'arguments': {'path': 'app.py'},
                'reason': 'Read the target file first.',
            }
        ],
        'allowed_tools': ['read_file'],
        'forbidden_tool_calls': [
            {
                'tool': 'search_owasp_reference',
                'reason': 'A security audit was not requested.',
            }
        ],
        'procedure_overrides': ['Read the file before answering.'],
    }


def test_requested_skill_result_preserves_null_skill_name_for_compatibility():
    result = RequestedSkillResult(
        status='ok',
        arguments={'path': 'app.py'},
        selection={
            'status': 'ok',
            'skill_name': None,
            'selection_reason': 'no relevant skill candidates found',
        },
        message='No relevant skill is available.',
    )

    assert result.to_payload() == {
        'status': 'ok',
        'skill_name': None,
        'arguments': {'path': 'app.py'},
        'selection': {
            'status': 'ok',
            'skill_name': None,
            'selection_reason': 'no relevant skill candidates found',
            'forced': False,
            'candidates': [],
            'rejected_candidates': [],
        },
        'message': 'No relevant skill is available.',
    }


def test_requested_skill_result_default_lists_are_not_shared():
    first = RequestedSkillResult(status='ok')
    second = RequestedSkillResult(status='ok')

    first.tools_required.append('read_file')
    first.preconditions.append('A path is available.')
    first.when_to_use.append('Use for code explanation.')
    first.when_not_to_use.append('Do not use for security audits.')
    first.exclusions.append('security_review')

    assert second.tools_required == []
    assert second.preconditions == []
    assert second.when_to_use == []
    assert second.when_not_to_use == []
    assert second.exclusions == []


def test_requested_skill_result_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RequestedSkillResult(status='ok', unexpected='value')


def test_requested_skill_result_rejects_invalid_nested_selection():
    with pytest.raises(ValidationError):
        RequestedSkillResult(
            status='ok',
            selection={'status': 'pending'},
        )


def test_requested_skill_result_rejects_invalid_nested_guidance():
    with pytest.raises(ValidationError, match='recommended tools must be allowed'):
        RequestedSkillResult(
            status='ok',
            guidance={
                'resolved_task_type': 'owasp_security_review',
                'allowed_tools': ['search_owasp_reference'],
                'recommended_tool_calls': [{'tool': 'discover_review_targets'}],
            },
        )
