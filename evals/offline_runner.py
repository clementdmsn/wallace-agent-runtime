from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from agent.skill_policy import (
    reset_skill_state,
    set_skill_state_from_selection,
    validate_final_response_against_skill_policy,
    validate_tool_call_against_skill_policy,
)
from contracts.evals import ExpectedToolStep, OfflineEvalDocument, OfflineEvalScenario, SkillFixture
from skills import selection
from skills.guidance import build_execution_guidance
from skills.skills_registry import Skill


DEFAULT_SCENARIO_PATH = Path(__file__).resolve().parent / 'scenarios' / 'agent_contracts.json'


@dataclass
class EvalAgent:
    active_skill_name: str | None = None
    active_skill_policy: dict[str, Any] | None = None
    skill_tool_call_index: int = 0
    verified_symbols_by_path: dict[str, set[str]] | None = None
    owasp_reference_search_count: int = 0

    def __post_init__(self) -> None:
        if self.active_skill_policy is None:
            self.active_skill_policy = {}
        if self.verified_symbols_by_path is None:
            self.verified_symbols_by_path = {}


def skill_from_payload(payload: SkillFixture | dict[str, Any]) -> Skill:
    if isinstance(payload, SkillFixture):
        payload = payload.to_payload()
    return Skill(
        name=str(payload['name']),
        description=str(payload.get('description', payload.get('summary', payload['name']))),
        implementation_name=str(payload.get('implementation_name', payload['name'])),
        parameters=dict(payload.get('parameters') or {'type': 'object', 'properties': {}, 'required': []}),
        procedure=str(payload.get('procedure', '')),
        metadata_path=str(payload.get('metadata_path', '')),
        procedure_path=str(payload.get('procedure_path', '')),
        when_to_use=tuple(payload.get('when_to_use') or ()),
        when_not_to_use=tuple(payload.get('when_not_to_use') or ()),
        examples=tuple(payload.get('examples') or ()),
        category=str(payload.get('category', 'general')),
        tags=frozenset(str(item) for item in payload.get('tags') or ()),
        supported_actions=frozenset(str(item) for item in payload.get('supported_actions') or ()),
        supported_domains=frozenset(str(item) for item in payload.get('supported_domains') or ()),
        supported_filetypes=frozenset(str(item) for item in payload.get('supported_filetypes') or ()),
        required_args=frozenset(str(item) for item in payload.get('required_args') or ()),
        tools_required=tuple(str(item) for item in payload.get('tools_required') or ()),
        exclusions=tuple(payload.get('exclusions') or ()),
        preconditions=tuple(payload.get('preconditions') or ()),
        priority=int(payload.get('priority', 0)),
        specificity=int(payload.get('specificity', 0)),
        default_score=float(payload.get('default_score', 0.5)),
    )


def load_eval_document(path: Path = DEFAULT_SCENARIO_PATH) -> OfflineEvalDocument:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('eval scenario file must contain a versioned document object')
    return OfflineEvalDocument(**payload)


def load_scenarios(path: Path = DEFAULT_SCENARIO_PATH) -> list[OfflineEvalScenario]:
    return load_eval_document(path).scenarios


def _coerce_scenario(scenario: OfflineEvalScenario | dict[str, Any]) -> OfflineEvalScenario:
    if isinstance(scenario, OfflineEvalScenario):
        return scenario
    return OfflineEvalScenario(**scenario)


def _candidate_retriever(skills_by_name: dict[str, Skill], scenario: OfflineEvalScenario):
    matches = scenario.candidate_matches
    if not matches:
        matches = [{'skill_name': name, 'distance': float(index)} for index, name in enumerate(skills_by_name)]

    def retrieve(_skills_by_name: dict[str, Skill], _user_text: str, _arguments: dict[str, Any], k: int = 8):
        candidates = []
        for match in matches[:k]:
            match_payload = match.to_payload() if hasattr(match, 'to_payload') else match
            skill_name = match_payload.get('skill_name')
            skill = skills_by_name.get(str(skill_name))
            if skill is not None:
                candidates.append((skill, dict(match_payload)))
        return candidates

    return retrieve


def choose_with_injected_candidates(
    skills_by_name: dict[str, Skill],
    scenario: OfflineEvalScenario | dict[str, Any],
    prompt: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    scenario = _coerce_scenario(scenario)
    original_retrieve = selection.retrieve_skill_candidates
    original_record = selection.record_skill_event
    original_bonus = selection.get_skill_score_bonus
    try:
        selection.retrieve_skill_candidates = _candidate_retriever(skills_by_name, scenario)
        selection.record_skill_event = lambda skill_name, event: None
        selection.get_skill_score_bonus = lambda skill_name: 0.0
        return selection.choose_skill_for_intent(
            skills_by_name,
            prompt,
            arguments,
            k=scenario.k,
            threshold=scenario.threshold,
        )
    finally:
        selection.retrieve_skill_candidates = original_retrieve
        selection.record_skill_event = original_record
        selection.get_skill_score_bonus = original_bonus


def _expect_equal(errors: list[str], label: str, actual: Any, expected: Any) -> None:
    if expected is not None and actual != expected:
        errors.append(f'{label}: expected {expected!r}, got {actual!r}')


def _expect_contains_all(errors: list[str], label: str, actual: list[Any], expected: list[Any]) -> None:
    missing = [item for item in expected if item not in actual]
    if missing:
        errors.append(f'{label}: missing {missing!r}; actual {actual!r}')


def apply_tool_sequence(
    agent: EvalAgent,
    tool_sequence: list[ExpectedToolStep] | list[dict[str, Any]],
    errors: list[str],
) -> list[dict[str, Any]]:
    results = []
    for index, step in enumerate(tool_sequence):
        step = ExpectedToolStep(**step) if isinstance(step, dict) else step
        tool = step.tool
        args = cast(dict[str, Any], step.arguments)
        expected = str(step.expect)
        policy_error = validate_tool_call_against_skill_policy(agent, tool, args)
        actual = 'blocked' if policy_error is not None else 'allowed'
        if actual != expected:
            errors.append(f'tool_sequence[{index}] {tool}: expected {expected}, got {actual}; error={policy_error}')
        if policy_error is None:
            agent.skill_tool_call_index += 1
            if tool == 'list_code_symbols':
                path = args.get('path')
                symbols = step.verified_symbols
                if isinstance(path, str):
                    agent.verified_symbols_by_path[path] = {str(symbol) for symbol in symbols}
            if tool == 'search_owasp_reference':
                agent.owasp_reference_search_count += 1
        results.append({'tool': tool, 'expected': expected, 'actual': actual, 'policy_error': policy_error})
    return results


def run_scenario(scenario: OfflineEvalScenario | dict[str, Any]) -> dict[str, Any]:
    scenario = _coerce_scenario(scenario)
    errors: list[str] = []
    prompt = scenario.prompt
    arguments = cast(dict[str, Any], scenario.arguments)
    skills_by_name = {
        skill.name: skill
        for skill in (skill_from_payload(payload) for payload in scenario.skills)
    }

    choice = choose_with_injected_candidates(skills_by_name, scenario, prompt, arguments)
    expected_skill = scenario.expected_skill
    _expect_equal(errors, 'selected skill', choice.get('skill_name'), expected_skill)

    guidance: dict[str, Any] | None = None
    selected_skill = skills_by_name.get(str(choice.get('skill_name')))
    if selected_skill is not None:
        guidance = build_execution_guidance(selected_skill, prompt, dict(arguments))
        _expect_equal(
            errors,
            'resolved task type',
            guidance.get('resolved_task_type'),
            scenario.expected_resolved_task_type,
        )
        _expect_contains_all(
            errors,
            'recommended tools',
            [item.get('tool') for item in guidance.get('recommended_tool_calls') or []],
            list(scenario.must_recommend_tools),
        )
        _expect_contains_all(
            errors,
            'allowed tools',
            list(guidance.get('allowed_tools') or []),
            list(scenario.must_allow_tools),
        )

    agent = EvalAgent()
    reset_skill_state(agent)
    if selected_skill is not None and guidance is not None:
        set_skill_state_from_selection(agent, {'skill_name': selected_skill.name, **guidance})

    tool_results = apply_tool_sequence(agent, scenario.tool_sequence, errors)

    final_policy_error = None
    if scenario.final_answer is not None:
        content = scenario.final_answer.content
        final_policy_error = validate_final_response_against_skill_policy(agent, content)
        expected_blocked = scenario.final_answer.expect_blocked
        actual_blocked = final_policy_error is not None
        if actual_blocked != expected_blocked:
            errors.append(
                f'final_answer: expected blocked={expected_blocked}, got blocked={actual_blocked}; '
                f'error={final_policy_error}'
            )

    return {
        'name': scenario.name,
        'status': 'pass' if not errors else 'fail',
        'errors': errors,
        'choice': choice,
        'guidance': guidance,
        'tool_results': tool_results,
        'final_policy_error': final_policy_error,
    }


def run_scenarios(scenarios: list[OfflineEvalScenario] | list[dict[str, Any]]) -> dict[str, Any]:
    results = [run_scenario(scenario) for scenario in scenarios]
    failed = [result for result in results if result['status'] != 'pass']
    return {
        'status': 'pass' if not failed else 'fail',
        'total': len(results),
        'passed': len(results) - len(failed),
        'failed': len(failed),
        'results': results,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Offline Agent Eval Report",
        '',
        f"Status: {report['status']}",
        f"Passed: {report['passed']}/{report['total']}",
        '',
    ]
    for result in report['results']:
        marker = 'PASS' if result['status'] == 'pass' else 'FAIL'
        lines.append(f"## {marker}: {result['name']}")
        selected = result.get('choice', {}).get('skill_name')
        lines.append(f"- selected_skill: {selected}")
        guidance = result.get('guidance') or {}
        if guidance:
            lines.append(f"- resolved_task_type: {guidance.get('resolved_task_type')}")
            tools = [item.get('tool') for item in guidance.get('recommended_tool_calls') or []]
            lines.append(f"- recommended_tools: {tools}")
        for error in result.get('errors') or []:
            lines.append(f"- error: {error}")
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description='Run deterministic offline Wallace agent contract evals.')
    parser.add_argument('scenario_file', nargs='?', default=str(DEFAULT_SCENARIO_PATH))
    parser.add_argument('--json', action='store_true', help='Print JSON instead of markdown.')
    args = parser.parse_args()

    report = run_scenarios(load_scenarios(Path(args.scenario_file)))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(markdown_report(report), end='')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
