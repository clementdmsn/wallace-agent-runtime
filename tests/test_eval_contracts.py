from __future__ import annotations

import json
import math

import pytest
from pydantic import ValidationError

from contracts.evals import OfflineEvalDocument
from evals.offline_runner import DEFAULT_SCENARIO_PATH


def valid_document_payload() -> dict[str, object]:
    return {
        'schema_version': 1,
        'scenarios': [
            {
                'name': 'code_overview_uses_summary_tool',
                'prompt': 'Explain auth.py',
                'arguments': {'path': 'auth.py'},
                'expected_skill': 'code_explainer',
                'expected_resolved_task_type': 'whole_file_code_overview',
                'candidate_matches': [{'skill_name': 'code_explainer', 'distance': 0.1}],
                'must_recommend_tools': ['summarize_code_file'],
                'must_allow_tools': ['summarize_code_file'],
                'skills': [
                    {
                        'name': 'code_explainer',
                        'description': 'Explain code files and functions.',
                        'category': 'code',
                        'tags': ['explain', 'code', 'python'],
                        'supported_actions': ['summarize'],
                        'supported_domains': ['code'],
                        'supported_filetypes': ['py'],
                        'required_args': ['path'],
                        'parameters': {
                            'type': 'object',
                            'properties': {'path': {'type': 'string'}},
                            'required': ['path'],
                            'additionalProperties': False,
                        },
                        'tools_required': ['summarize_code_file', 'read_file'],
                        'priority': 3,
                        'specificity': 4,
                        'default_score': 0.7,
                    }
                ],
                'tool_sequence': [
                    {
                        'tool': 'summarize_code_file',
                        'arguments': {'path': 'auth.py'},
                        'expect': 'allowed',
                    }
                ],
                'final_answer': {
                    'content': 'Summary cites the loaded file.',
                    'expect_blocked': False,
                },
                'k': 5,
                'threshold': 8.0,
            }
        ],
    }


def test_checked_in_offline_eval_document_matches_contract():
    payload = json.loads(DEFAULT_SCENARIO_PATH.read_text(encoding='utf-8'))

    document = OfflineEvalDocument(**payload)

    assert document.schema_version == 1
    assert len(document.scenarios) == 10


def test_offline_eval_document_serializes_valid_payload():
    document = OfflineEvalDocument(**valid_document_payload())

    assert document.to_payload()['schema_version'] == 1
    assert document.to_payload()['scenarios'][0]['tool_sequence'][0]['expect'] == 'allowed'


def test_offline_eval_document_requires_schema_version():
    payload = valid_document_payload()
    payload.pop('schema_version')

    with pytest.raises(ValidationError):
        OfflineEvalDocument(**payload)


def test_offline_eval_document_rejects_unknown_schema_version():
    payload = valid_document_payload()
    payload['schema_version'] = 2

    with pytest.raises(ValidationError):
        OfflineEvalDocument(**payload)


def test_offline_eval_document_rejects_duplicate_scenario_names():
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenarios.append(dict(scenarios[0]))

    with pytest.raises(ValidationError, match='scenario names must be unique'):
        OfflineEvalDocument(**payload)


@pytest.mark.parametrize(
    ('field_name', 'replacement'),
    [
        ('name', ''),
        ('prompt', ''),
    ],
)
def test_offline_eval_scenario_rejects_empty_required_text(field_name: str, replacement: str):
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenario = scenarios[0]
    assert isinstance(scenario, dict)
    scenario[field_name] = replacement

    with pytest.raises(ValidationError):
        OfflineEvalDocument(**payload)


def test_offline_eval_scenario_rejects_unknown_expected_skill():
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenario = scenarios[0]
    assert isinstance(scenario, dict)
    scenario['expected_skill'] = 'missing_skill'

    with pytest.raises(ValidationError, match='expected_skill references unknown skill fixture'):
        OfflineEvalDocument(**payload)


@pytest.mark.parametrize(
    ('field_name', 'replacement'),
    [
        ('expected_resolved_task_type', 'whole_file_code_overview'),
        ('must_recommend_tools', ['summarize_code_file']),
        ('must_allow_tools', ['summarize_code_file']),
    ],
)
def test_offline_eval_scenario_rejects_skill_policy_expectations_without_expected_skill(
    field_name: str,
    replacement: object,
):
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenario = scenarios[0]
    assert isinstance(scenario, dict)
    scenario['expected_skill'] = None
    scenario.pop('expected_resolved_task_type')
    scenario['must_recommend_tools'] = []
    scenario['must_allow_tools'] = []
    scenario[field_name] = replacement

    with pytest.raises(ValidationError, match='skill-policy expectations require expected_skill'):
        OfflineEvalDocument(**payload)


def test_offline_eval_scenario_rejects_unknown_candidate_skill():
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenario = scenarios[0]
    assert isinstance(scenario, dict)
    scenario['candidate_matches'] = [{'skill_name': 'missing_skill', 'distance': 0.1}]

    with pytest.raises(ValidationError, match='candidate_matches reference unknown skill fixtures'):
        OfflineEvalDocument(**payload)


def test_offline_eval_scenario_rejects_empty_tool_names():
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenario = scenarios[0]
    assert isinstance(scenario, dict)
    scenario['tool_sequence'] = [{'tool': '', 'expect': 'allowed'}]

    with pytest.raises(ValidationError):
        OfflineEvalDocument(**payload)


def test_offline_eval_scenario_rejects_unknown_policy_expectation():
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenario = scenarios[0]
    assert isinstance(scenario, dict)
    scenario['tool_sequence'] = [{'tool': 'read_file', 'expect': 'maybe'}]

    with pytest.raises(ValidationError):
        OfflineEvalDocument(**payload)


@pytest.mark.parametrize(
    ('field_name', 'replacement'),
    [
        ('k', 0),
        ('threshold', -0.1),
    ],
)
def test_offline_eval_scenario_rejects_unbounded_runtime_numbers(field_name: str, replacement: float):
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenario = scenarios[0]
    assert isinstance(scenario, dict)
    scenario[field_name] = replacement

    with pytest.raises(ValidationError):
        OfflineEvalDocument(**payload)


@pytest.mark.parametrize(
    ('field_name', 'replacement'),
    [
        ('priority', -1),
        ('specificity', -1),
        ('default_score', 1.1),
    ],
)
def test_offline_eval_scenario_rejects_unbounded_skill_numbers(field_name: str, replacement: float):
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenario = scenarios[0]
    assert isinstance(scenario, dict)
    skill = scenario['skills'][0]
    assert isinstance(skill, dict)
    skill[field_name] = replacement

    with pytest.raises(ValidationError):
        OfflineEvalDocument(**payload)


def test_offline_eval_scenario_rejects_negative_candidate_distance():
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenario = scenarios[0]
    assert isinstance(scenario, dict)
    scenario['candidate_matches'] = [{'skill_name': 'code_explainer', 'distance': -0.1}]

    with pytest.raises(ValidationError):
        OfflineEvalDocument(**payload)


def test_offline_eval_scenario_rejects_non_finite_json_arguments():
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenario = scenarios[0]
    assert isinstance(scenario, dict)
    scenario['arguments'] = {'path': 'auth.py', 'score': math.inf}

    with pytest.raises(ValidationError):
        OfflineEvalDocument(**payload)


def test_offline_eval_scenario_rejects_tool_specific_fields_on_wrong_step():
    payload = valid_document_payload()
    scenarios = payload['scenarios']
    assert isinstance(scenarios, list)
    scenario = scenarios[0]
    assert isinstance(scenario, dict)
    scenario['tool_sequence'] = [
        {
            'tool': 'read_file',
            'arguments': {'path': 'auth.py'},
            'verified_symbols': ['login'],
            'expect': 'allowed',
        }
    ]

    with pytest.raises(ValidationError, match='verified_symbols is only valid'):
        OfflineEvalDocument(**payload)
