from __future__ import annotations

from pathlib import Path
from typing import Any

from skills.intent import extract_intent, extract_symbol_arg
from skills.skills_registry import Skill


# Guidance converts a selected skill into concrete tool restrictions and ordered
# tool recommendations for ambiguous tasks.
def explicit_symbol_from_intent(intent_text: str, arguments: dict[str, Any]) -> str | None:
    # Model-provided symbols may be guesses; only user-text symbols are trusted.
    return extract_symbol_arg(intent_text, arguments)


def merge_and_sanitize_intent_args(intent_text: str, arguments: dict[str, Any]) -> dict[str, Any]:
    inferred_args = extract_intent(intent_text).get('args', {})
    merged_args = {**inferred_args, **arguments}

    explicit_symbol = inferred_args.get('symbol')
    if explicit_symbol:
        merged_args['symbol'] = explicit_symbol
    else:
        merged_args.pop('symbol', None)

    return merged_args


def build_execution_guidance(skill: Skill, intent_text: str, arguments: dict[str, Any]) -> dict[str, Any]:
    path = arguments.get('path')
    symbol = explicit_symbol_from_intent(intent_text, arguments)
    action = extract_intent(intent_text).get('action')

    guidance: dict[str, Any] = {
        'resolved_task_type': 'generic_skill_procedure',
        'recommended_tool_calls': [],
        'allowed_tools': list(skill.tools_required),
        'forbidden_tool_calls': [],
        'procedure_overrides': [],
    }

    is_code_path = isinstance(path, str) and Path(path).suffix.lower() in {
        '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.rs', '.php', '.rb', '.c', '.cpp', '.h', '.hpp'
    }

    if skill.name == 'owasp_security_review':
        guidance['resolved_task_type'] = 'owasp_security_review'
        guidance['allowed_tools'] = list(skill.tools_required)
        if isinstance(path, str) and path.strip():
            guidance['recommended_tool_calls'] = [
                {
                    'tool': 'discover_review_targets',
                    'arguments': {'root': path, 'max_files': 20},
                    'reason': 'OWASP security review must first discover the bounded audit target set.',
                }
            ]
        guidance['procedure_overrides'] = [
            'After reviewing concrete evidence, call search_owasp_reference before any final answer.',
            'Every finding must cite a returned OWASP source/version/reference_id/title/url. Do not cite OWASP from memory.',
            'For short single-file audits, prefer discover_review_targets, read_file_with_line_numbers, then search_owasp_reference. Use symbol tools only when they add useful security evidence.',
        ]
        return guidance

    if is_code_path and not symbol and action in {'summarize', 'unknown'}:
        guidance['resolved_task_type'] = 'whole_file_code_overview'
        guidance['allowed_tools'] = ['summarize_code_file']
        guidance['recommended_tool_calls'] = [
            {
                'tool': 'summarize_code_file',
                'arguments': {'path': path},
                'reason': 'User requested an explanation/overview of a code file and did not provide a specific symbol.',
            }
        ]
        guidance['forbidden_tool_calls'] = [
            {
                'tool': 'explain_function_for_model',
                'reason': 'No explicit symbol was provided. Do not guess symbols such as main.',
            },
            {
                'tool': 'read_file',
                'reason': 'summarize_code_file is the dedicated compact code-overview tool for whole-file explanation.',
            },
        ]
        guidance['procedure_overrides'] = [
            'Treat this as a whole-file code overview request, not a specific-function request.',
            'Call summarize_code_file with the returned path exactly once before answering.',
            'Do not guess or invent a symbol name.',
            'Do not call read_file unless summarize_code_file fails and the user explicitly asks to read raw contents.',
            'Base the answer on the summarize_code_file result.',
        ]
        return guidance

    if is_code_path and symbol:
        arguments['symbol'] = symbol
        guidance['resolved_task_type'] = 'specific_function_explanation'
        guidance['allowed_tools'] = ['list_code_symbols', 'explain_function_for_model']
        guidance['recommended_tool_calls'] = [
            {
                'tool': 'list_code_symbols',
                'arguments': {'path': path},
                'reason': 'Verify available symbols before explaining a specific function.',
            },
            {
                'tool': 'explain_function_for_model',
                'arguments': {'path': path, 'symbol': symbol},
                'reason': 'Explain only the explicitly requested symbol after it has been discovered from the file.',
            },
        ]
        guidance['forbidden_tool_calls'] = [
            {
                'tool': 'read_file',
                'reason': 'Use deterministic symbol tools instead of raw file reading for function explanation.',
            }
        ]
        guidance['procedure_overrides'] = [
            'Treat this as a specific-function explanation request.',
            'First call list_code_symbols with the returned path to discover valid symbols.',
            'Then call explain_function_for_model only if the requested symbol appears in the discovered symbols.',
            'Do not substitute another symbol. If the requested symbol is missing, report that failure explicitly.',
            'Base the answer on the tool result.',
        ]
        return guidance

    return guidance
