from __future__ import annotations

from agent.agent_skill_policy import (
    remember_owasp_reference_search,
    remember_verified_symbols,
    reset_skill_state,
    set_skill_state_from_selection,
    validate_final_response_against_skill_policy,
    validate_tool_call_against_skill_policy,
)


class FakeAgent:
    def __init__(self):
        self.active_skill_name = None
        self.active_skill_policy = {}
        self.skill_tool_call_index = 0
        self.verified_symbols_by_path = {}
        self.owasp_reference_search_count = 0


def test_direct_function_explanation_requires_verified_symbol():
    agent = FakeAgent()

    result = validate_tool_call_against_skill_policy(
        agent,
        'explain_function_for_model',
        {'path': 'auth.py', 'symbol': 'login'},
    )

    assert result is not None
    assert result['error'] == 'symbol must be discovered before explain_function_for_model'


def test_direct_function_explanation_allows_verified_symbol():
    agent = FakeAgent()
    agent.verified_symbols_by_path = {'auth.py': {'login'}}

    result = validate_tool_call_against_skill_policy(
        agent,
        'explain_function_for_model',
        {'path': 'auth.py', 'symbol': 'login'},
    )

    assert result is None


def test_active_skill_blocks_direct_skill_file_writes_before_generic_tool_policy():
    agent = FakeAgent()
    agent.active_skill_name = 'create_new_skill'
    agent.active_skill_policy = {'allowed_tools': ['create_skill']}

    result = validate_tool_call_against_skill_policy(
        agent,
        'write_file',
        {'path': 'skill_catalog/metadatas/debug_function.json', 'content': '{}'},
    )

    assert result is not None
    assert result['error'] == 'direct skill file writes are blocked by active skill policy'
    assert 'finalize_skill_draft' in result['message']


def test_active_skill_allows_draft_file_repairs():
    agent = FakeAgent()
    agent.active_skill_name = 'create_new_skill'
    agent.active_skill_policy = {'allowed_tools': ['create_skill']}

    result = validate_tool_call_against_skill_policy(
        agent,
        'replace_in_file',
        {'path': 'skills/drafts/debug_function.json', 'search': 'old', 'replace': 'new'},
    )

    assert result is None


def test_reset_and_set_skill_state_from_selection():
    agent = FakeAgent()
    agent.active_skill_name = 'old'
    agent.active_skill_policy = {'allowed_tools': ['read_file']}
    agent.skill_tool_call_index = 3
    agent.verified_symbols_by_path = {'a.py': {'f'}}

    reset_skill_state(agent)

    assert agent.active_skill_name is None
    assert agent.active_skill_policy == {}
    assert agent.skill_tool_call_index == 0
    assert agent.verified_symbols_by_path == {}
    assert agent.owasp_reference_search_count == 0

    set_skill_state_from_selection(agent, {
        'skill_name': 'inspect_symbol',
        'allowed_tools': ['list_code_symbols'],
        'forbidden_tool_calls': [{'tool': 'read_file', 'reason': 'Use parsed symbols.'}],
        'recommended_tool_calls': [{'tool': 'list_code_symbols', 'arguments': {'path': 'a.py'}}],
    })

    assert agent.active_skill_name == 'inspect_symbol'
    assert agent.active_skill_policy['allowed_tools'] == ['list_code_symbols']
    assert agent.skill_tool_call_index == 0


def test_remember_verified_symbols_stores_names_and_qualified_names():
    agent = FakeAgent()

    remember_verified_symbols(
        agent,
        'list_code_symbols',
        {'path': 'demo.py'},
        {
            'status': 'ok',
            'symbols': [
                {'name': 'local_name', 'qualified_name': 'Demo.local_name'},
                {'name': 'other'},
                'ignored',
            ],
        },
    )

    assert agent.verified_symbols_by_path['demo.py'] == {'local_name', 'Demo.local_name', 'other'}


def test_active_skill_blocks_tools_outside_allowed_set():
    agent = FakeAgent()
    agent.active_skill_name = 'inspect'
    agent.active_skill_policy = {'allowed_tools': ['list_code_symbols']}

    result = validate_tool_call_against_skill_policy(agent, 'read_file', {'path': 'demo.py'})

    assert result is not None
    assert result['provided_tool'] == 'read_file'
    assert result['allowed_tools'] == ['list_code_symbols']


def test_active_skill_blocks_forbidden_tool_call():
    agent = FakeAgent()
    agent.active_skill_name = 'inspect'
    agent.active_skill_policy = {
        'forbidden_tool_calls': [{'tool': 'read_file', 'reason': 'Use summarize_code_file.'}],
    }

    result = validate_tool_call_against_skill_policy(agent, 'read_file', {'path': 'demo.py'})

    assert result is not None
    assert result['error'] == 'tool call forbidden by active skill policy: read_file'
    assert result['message'] == 'Use summarize_code_file.'


def test_active_skill_enforces_recommended_tool_order_and_arguments():
    agent = FakeAgent()
    agent.active_skill_name = 'inspect'
    agent.active_skill_policy = {
        'recommended_tool_calls': [{'tool': 'list_code_symbols', 'arguments': {'path': 'demo.py'}}],
    }

    wrong_tool = validate_tool_call_against_skill_policy(agent, 'read_file', {'path': 'demo.py'})
    wrong_arg = validate_tool_call_against_skill_policy(agent, 'list_code_symbols', {'path': 'other.py'})
    ok = validate_tool_call_against_skill_policy(agent, 'list_code_symbols', {'path': 'demo.py'})

    assert wrong_tool is not None
    assert wrong_tool['expected_tool'] == 'list_code_symbols'
    assert wrong_arg is not None
    assert wrong_arg['error'] == 'argument mismatch for recommended tool call: path'
    assert ok is None


def test_active_skill_function_explanation_requires_explicit_and_verified_symbol():
    agent = FakeAgent()
    agent.active_skill_name = 'inspect'
    agent.active_skill_policy = {
        'allowed_tools': ['explain_function_for_model'],
        'recommended_tool_calls': [
            {'tool': 'explain_function_for_model', 'arguments': {'path': 'demo.py', 'symbol': 'target'}},
        ],
    }

    not_requested = validate_tool_call_against_skill_policy(
        agent,
        'explain_function_for_model',
        {'path': 'demo.py', 'symbol': 'other'},
    )
    not_verified = validate_tool_call_against_skill_policy(
        agent,
        'explain_function_for_model',
        {'path': 'demo.py', 'symbol': 'target'},
    )
    agent.verified_symbols_by_path = {'demo.py': {'target'}}
    ok = validate_tool_call_against_skill_policy(
        agent,
        'explain_function_for_model',
        {'path': 'demo.py', 'symbol': 'target'},
    )

    assert not_requested is not None
    assert not_requested['error'] == 'argument mismatch for recommended tool call: symbol'
    assert not_verified is not None
    assert not_verified['error'] == 'symbol must be discovered before explain_function_for_model'
    assert ok is None


def test_owasp_security_review_allows_discovered_symbol_explanation():
    agent = FakeAgent()
    agent.active_skill_name = 'owasp_security_review'
    agent.active_skill_policy = {
        'allowed_tools': ['list_code_symbols', 'explain_function_for_model', 'search_owasp_reference'],
    }
    agent.verified_symbols_by_path = {'security_easy.py': {'connect_to_service'}}

    ok = validate_tool_call_against_skill_policy(
        agent,
        'explain_function_for_model',
        {'path': 'security_easy.py', 'symbol': 'connect_to_service'},
    )
    missing = validate_tool_call_against_skill_policy(
        agent,
        'explain_function_for_model',
        {'path': 'security_easy.py', 'symbol': 'not_returned'},
    )

    assert ok is None
    assert missing is not None
    assert missing['error'] == 'symbol must be discovered before explain_function_for_model'


def test_owasp_security_review_final_response_requires_reference_search():
    agent = FakeAgent()
    agent.active_skill_name = 'owasp_security_review'

    blocked = validate_final_response_against_skill_policy(agent, 'Critical finding...')
    remember_owasp_reference_search(agent, 'search_owasp_reference', {'status': 'ok', 'matches': []})
    allowed = validate_final_response_against_skill_policy(agent, 'Critical finding...')

    assert blocked is not None
    assert blocked['required_tool'] == 'search_owasp_reference'
    assert agent.owasp_reference_search_count == 1
    assert allowed is None
