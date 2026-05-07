from __future__ import annotations

from skills.guidance import build_execution_guidance, merge_and_sanitize_intent_args
from skills.skills_registry import Skill


def make_skill() -> Skill:
    return Skill(
        name='code_explainer',
        description='Explain code files and functions.',
        implementation_name='code_explainer',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        procedure='Explain code using deterministic tools.',
        metadata_path='skills/metadatas/code_explainer.json',
        procedure_path='skills/procedures/code_explainer.md',
        tools_required=('summarize_code_file', 'list_code_symbols', 'explain_function_for_model', 'read_file'),
    )


def test_whole_file_guidance_for_code_path_without_symbol():
    guidance = build_execution_guidance(
        make_skill(),
        'Explain auth.py',
        {'path': 'auth.py'},
    )

    assert guidance['resolved_task_type'] == 'whole_file_code_overview'
    assert guidance['allowed_tools'] == ['summarize_code_file']
    assert guidance['recommended_tool_calls'] == [
        {
            'tool': 'summarize_code_file',
            'arguments': {'path': 'auth.py'},
            'reason': 'User requested an explanation/overview of a code file and did not provide a specific symbol.',
        }
    ]
    assert {item['tool'] for item in guidance['forbidden_tool_calls']} == {
        'explain_function_for_model',
        'read_file',
    }


def test_specific_function_guidance_for_explicit_symbol():
    guidance = build_execution_guidance(
        make_skill(),
        'Explain function login in auth.py',
        {'path': 'auth.py'},
    )

    assert guidance['resolved_task_type'] == 'specific_function_explanation'
    assert guidance['allowed_tools'] == ['list_code_symbols', 'explain_function_for_model']
    assert guidance['recommended_tool_calls'][0]['tool'] == 'list_code_symbols'
    assert guidance['recommended_tool_calls'][1]['tool'] == 'explain_function_for_model'
    assert guidance['recommended_tool_calls'][1]['arguments'] == {
        'path': 'auth.py',
        'symbol': 'login',
    }


def test_merge_and_sanitize_args_removes_guessed_symbol():
    args = merge_and_sanitize_intent_args(
        'Explain auth.py',
        {'path': 'auth.py', 'symbol': 'main'},
    )

    assert args == {'path': 'auth.py'}


def test_merge_and_sanitize_args_keeps_user_explicit_symbol_over_argument_guess():
    args = merge_and_sanitize_intent_args(
        'Explain function authenticate in auth.py',
        {'path': 'auth.py', 'symbol': 'main'},
    )

    assert args == {'path': 'auth.py', 'symbol': 'authenticate'}


def test_generic_guidance_keeps_skill_required_tools_for_non_code_path():
    skill = make_skill()

    guidance = build_execution_guidance(
        skill,
        'Explain README.md',
        {'path': 'README.md'},
    )

    assert guidance == {
        'resolved_task_type': 'generic_skill_procedure',
        'recommended_tool_calls': [],
        'allowed_tools': list(skill.tools_required),
        'forbidden_tool_calls': [],
        'procedure_overrides': [],
    }


def test_owasp_guidance_recommends_discovery_when_path_is_available():
    skill = Skill(
        name='owasp_security_review',
        description='Review security issues.',
        implementation_name='owasp_security_review',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        tools_required=('discover_review_targets', 'read_file_with_line_numbers', 'search_owasp_reference'),
    )

    guidance = build_execution_guidance(
        skill,
        'security audit app.py',
        {'path': 'app.py'},
    )

    assert guidance['resolved_task_type'] == 'owasp_security_review'
    assert guidance['allowed_tools'] == [
        'discover_review_targets',
        'read_file_with_line_numbers',
        'search_owasp_reference',
    ]
    assert guidance['recommended_tool_calls'] == [
        {
            'tool': 'discover_review_targets',
            'arguments': {'root': 'app.py', 'max_files': 20},
            'reason': 'OWASP security review must first discover the bounded audit target set.',
        }
    ]
    assert 'search_owasp_reference' in guidance['procedure_overrides'][0]


def test_owasp_guidance_without_path_has_policy_overrides_but_no_initial_tool():
    skill = Skill(
        name='owasp_security_review',
        description='Review security issues.',
        implementation_name='owasp_security_review',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        tools_required=('discover_review_targets', 'search_owasp_reference'),
    )

    guidance = build_execution_guidance(skill, 'security audit the project', {})

    assert guidance['resolved_task_type'] == 'owasp_security_review'
    assert guidance['recommended_tool_calls'] == []
    assert guidance['procedure_overrides']
