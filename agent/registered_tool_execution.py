from __future__ import annotations

from typing import Any

from agent.agent_skill_policy import (
    remember_owasp_reference_search,
    remember_verified_symbols,
    validate_tool_call_against_skill_policy,
)
from agent.tool_call_parsing import parse_tool_args
from agent.tool_result_formatting import ToolExecutionResult
from contracts.tool_results import CurlResult
from skills.stats import record_skill_event
from tools.tools import TOOLS


def record_active_skill_event(agent: Any, event: str) -> None:
    if agent.active_skill_name:
        record_skill_event(agent.active_skill_name, event)


def apply_skill_authoring_retry_policy(agent: Any, call_name: str, result: object) -> object:
    if call_name not in {'create_skill', 'finalize_skill_draft', 'repair_skill_draft'} or not isinstance(result, dict):
        return result

    if result.get('status') == 'ok':
        agent.skill_creation_failures = 0
        return result

    if result.get('error') != 'json_payload failed skill quality validation':
        return result

    agent.skill_creation_failures = getattr(agent, 'skill_creation_failures', 0) + 1
    if agent.skill_creation_failures < 3:
        return result

    return {
        **result,
        'retry_limit_reached': True,
        'message': (
            'Skill draft validation failed after 3 attempts. Stop retrying and show the user '
            'the draft paths and validation errors.'
        ),
    }


def validate_registered_tool_result(call_name: str, result: object) -> object:
    if call_name == 'curl_url' and isinstance(result, dict):
        return CurlResult(**result).to_payload()
    return result


def execute_registered_tool(agent: Any, call_name: str, args: dict[str, Any]) -> object:
    policy_error = validate_tool_call_against_skill_policy(agent, call_name, args)
    if policy_error is not None:
        record_active_skill_event(agent, 'failure')
        return policy_error

    record_active_skill_event(agent, 'used')
    result = TOOLS[call_name].func(**args)
    result = validate_registered_tool_result(call_name, result)
    result = apply_skill_authoring_retry_policy(agent, call_name, result)
    remember_verified_symbols(agent, call_name, args, result)
    remember_owasp_reference_search(agent, call_name, result)

    if agent.active_skill_name:
        agent.skill_tool_call_index += 1
        if isinstance(result, dict) and result.get('status') == 'ok':
            record_skill_event(agent.active_skill_name, 'success')
        else:
            record_skill_event(agent.active_skill_name, 'failure')

    return result


def run_tool(agent: Any, call_name: str, raw_args: str) -> ToolExecutionResult:
    kind = 'tool'
    args, parse_error = parse_tool_args(raw_args)
    if parse_error is not None:
        return ToolExecutionResult(kind=kind, args={}, result=parse_error)

    assert args is not None
    if call_name not in TOOLS:
        return ToolExecutionResult(
            kind=kind,
            args=args,
            result={
                'status': 'error',
                'error': f'unknown tool: {call_name}',
                'message': 'Only registered tools are executable.',
            },
        )

    try:
        result = execute_registered_tool(agent, call_name, args)
    except Exception as exc:
        record_active_skill_event(agent, 'failure')
        result = {'status': 'error', 'error': str(exc)}

    return ToolExecutionResult(kind=kind, args=args, result=result)
