from __future__ import annotations

from typing import Any

def reset_skill_state(agent: Any) -> None:
    agent.active_skill_name = None
    agent.active_skill_policy = {}
    agent.skill_tool_call_index = 0
    agent.verified_symbols_by_path = {}
    agent.owasp_reference_search_count = 0

def set_skill_state_from_selection(agent: Any, result: dict[str, Any]) -> None:
    selected = result.get('skill_name')
    agent.active_skill_name = str(selected) if selected else None
    agent.active_skill_policy = {
        'allowed_tools': result.get('allowed_tools') or [],
        'forbidden_tool_calls': result.get('forbidden_tool_calls') or [],
        'recommended_tool_calls': result.get('recommended_tool_calls') or [],
    }
    agent.skill_tool_call_index = 0
    agent.verified_symbols_by_path = {}
    agent.owasp_reference_search_count = 0

def remember_verified_symbols(
    agent: Any,
    call_name: str,
    args: dict[str, Any],
    result: object,
) -> None:
    if call_name != 'list_code_symbols' or not isinstance(result, dict):
        return
    if result.get('status') != 'ok':
        return

    path = result.get('path') or args.get('path')
    if not isinstance(path, str) or not path:
        return

    verified: set[str] = set()
    for item in result.get('symbols') or result.get('content') or []:
        if not isinstance(item, dict):
            continue
        for key in ('name', 'qualified_name'):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                verified.add(value.strip())

    agent.verified_symbols_by_path[path] = verified

def remember_owasp_reference_search(agent: Any, call_name: str, result: object) -> None:
    if call_name != 'search_owasp_reference' or not isinstance(result, dict):
        return
    if result.get('status') != 'ok':
        return
    agent.owasp_reference_search_count = getattr(agent, 'owasp_reference_search_count', 0) + 1

def validate_final_response_against_skill_policy(agent: Any, content: str) -> dict[str, Any] | None:
    if agent.active_skill_name != 'owasp_security_review':
        return None
    if getattr(agent, 'owasp_reference_search_count', 0) > 0:
        return None

    return {
        'status': 'error',
        'error': 'OWASP security review final answer blocked: missing search_owasp_reference call',
        'message': (
            'The active owasp_security_review skill requires OWASP retrieval before any final audit answer. '
            'Call search_owasp_reference with the concrete concern found in the reviewed evidence, then answer '
            'using only returned OWASP source/version/reference metadata for citations.'
        ),
        'required_tool': 'search_owasp_reference',
        'active_skill_name': agent.active_skill_name,
        'blocked_content_chars': len(content),
    }

def validate_tool_call_against_skill_policy(
    agent: Any,
    call_name: str,
    args: dict[str, Any],
) -> dict[str, Any] | None:
    policy = agent.active_skill_policy or {}
    recommended = policy.get('recommended_tool_calls') or []

    if not agent.active_skill_name:
        if call_name == 'explain_function_for_model':
            path = args.get('path')
            symbol = args.get('symbol')
            verified = agent.verified_symbols_by_path.get(path if isinstance(path, str) else '', set())
            if not isinstance(symbol, str) or symbol not in verified:
                return {
                    'status': 'error',
                    'error': 'symbol must be discovered before explain_function_for_model',
                    'message': 'Call list_code_symbols first, then use only a symbol that appears in the returned symbols.',
                    'path': path,
                    'symbol': symbol,
                    'verified_symbols': sorted(verified),
                }
        return None

    if agent.active_skill_name and call_name in {'read_file', 'write_file', 'replace_in_file', 'append_to_file'}:
        path = args.get('path')
        if isinstance(path, str) and path.startswith('skills/drafts/'):
            return None
        if isinstance(path, str) and path.startswith((
            'skills/metadatas/',
            'skills/procedures/',
            'skill_catalog/metadatas/',
            'skill_catalog/procedures/',
        )):
            return {
                'status': 'error',
                'error': 'direct skill file writes are blocked by active skill policy',
                'message': 'Use create_skill/repair_skill_draft/finalize_skill_draft to create skill files. Edit only skills/drafts when repairing validation errors.',
                'path': path,
                'provided_tool': call_name,
            }

    allowed_tools = policy.get('allowed_tools') or []
    if allowed_tools and call_name not in allowed_tools:
        return {
            'status': 'error',
            'error': f'tool call blocked by active skill policy: {call_name}',
            'message': f'Allowed tools for {agent.active_skill_name}: {allowed_tools}',
            'allowed_tools': allowed_tools,
            'provided_tool': call_name,
        }

    for forbidden in policy.get('forbidden_tool_calls') or []:
        if forbidden.get('tool') == call_name:
            return {
                'status': 'error',
                'error': f'tool call forbidden by active skill policy: {call_name}',
                'message': forbidden.get('reason', 'Tool is forbidden for the selected skill context.'),
                'forbidden_tool_calls': policy.get('forbidden_tool_calls') or [],
                'provided_tool': call_name,
            }

    if agent.skill_tool_call_index < len(recommended):
        expected = recommended[agent.skill_tool_call_index]
        expected_tool = expected.get('tool')
        expected_args = expected.get('arguments') or {}

        if call_name != expected_tool:
            return {
                'status': 'error',
                'error': f'expected recommended tool call: {expected_tool}, got: {call_name}',
                'expected_tool': expected_tool,
                'provided_tool': call_name,
                'expected_arguments': expected_args,
                'provided_arguments': args,
                'recommended_tool_calls': recommended,
            }

        for key, expected_value in expected_args.items():
            if args.get(key) != expected_value:
                return {
                    'status': 'error',
                    'error': f'argument mismatch for recommended tool call: {key}',
                    'expected_tool': expected_tool,
                    'provided_tool': call_name,
                    'expected_arguments': expected_args,
                    'provided_arguments': args,
                    'recommended_tool_calls': recommended,
                }

    if call_name == 'explain_function_for_model':
        path = args.get('path')
        symbol = args.get('symbol')
        verified = agent.verified_symbols_by_path.get(path if isinstance(path, str) else '', set())

        if agent.active_skill_name == 'owasp_security_review':
            if isinstance(symbol, str) and symbol in verified:
                return None
            return {
                'status': 'error',
                'error': 'symbol must be discovered before explain_function_for_model',
                'message': 'For OWASP security review, call list_code_symbols first and use only a returned symbol.',
                'path': path,
                'symbol': symbol,
                'verified_symbols': sorted(verified),
            }

        # Function-level explanations must use an explicit requested symbol, not a guessed one.
        explicit_recommended_symbols = {
            call.get('arguments', {}).get('symbol')
            for call in recommended
            if isinstance(call, dict) and call.get('tool') == 'explain_function_for_model'
        }
        explicit_recommended_symbols = {
            value for value in explicit_recommended_symbols
            if isinstance(value, str) and value.strip()
        }

        if not explicit_recommended_symbols:
            return {
                'status': 'error',
                'error': 'no specific symbol was requested',
                'message': 'list_code_symbols may discover symbols, but the agent must not choose one for a whole-file explanation. Use summarize_code_file instead.',
                'path': path,
                'symbol': symbol,
                'allowed_tools': allowed_tools,
                'recommended_tool_calls': recommended,
            }

        if not isinstance(symbol, str) or symbol not in explicit_recommended_symbols:
            return {
                'status': 'error',
                'error': 'symbol was not explicitly requested',
                'message': 'Do not substitute or choose a discovered symbol. Use exactly the symbol requested in the active skill plan.',
                'path': path,
                'symbol': symbol,
                'explicit_requested_symbols': sorted(explicit_recommended_symbols),
                'verified_symbols': sorted(verified),
            }

        if symbol not in verified:
            return {
                'status': 'error',
                'error': 'symbol must be discovered before explain_function_for_model',
                'message': 'Call list_code_symbols first, then use the explicitly requested symbol only if it appears in the returned symbols.',
                'path': path,
                'symbol': symbol,
                'verified_symbols': sorted(verified),
            }

    return None
