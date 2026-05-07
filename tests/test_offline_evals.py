from __future__ import annotations

from evals.offline_runner import (
    DEFAULT_SCENARIO_PATH,
    load_scenarios,
    markdown_report,
    run_scenario,
    run_scenarios,
)


def test_default_offline_eval_scenarios_pass():
    report = run_scenarios(load_scenarios(DEFAULT_SCENARIO_PATH))

    assert report['status'] == 'pass'
    assert report['total'] == 10
    assert report['passed'] == 10
    assert report['failed'] == 0


def test_offline_eval_reports_failed_skill_contract():
    scenario = {
        'name': 'wrong_expected_skill',
        'prompt': 'Explain auth.py',
        'arguments': {'path': 'auth.py'},
        'expected_skill': 'missing_skill',
        'candidate_matches': [{'skill_name': 'code_explainer', 'distance': 0.1}],
        'skills': [
            {
                'name': 'code_explainer',
                'description': 'Explain code files.',
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
                'tools_required': ['summarize_code_file'],
                'default_score': 0.7,
            }
        ],
    }

    result = run_scenario(scenario)

    assert result['status'] == 'fail'
    assert "selected skill: expected 'missing_skill', got 'code_explainer'" in result['errors'][0]


def test_markdown_report_summarizes_pass_and_failure():
    report = {
        'status': 'fail',
        'total': 1,
        'passed': 0,
        'failed': 1,
        'results': [
            {
                'name': 'demo',
                'status': 'fail',
                'errors': ['bad contract'],
                'choice': {'skill_name': 'demo_skill'},
                'guidance': {
                    'resolved_task_type': 'demo',
                    'recommended_tool_calls': [{'tool': 'read_file'}],
                },
            }
        ],
    }

    markdown = markdown_report(report)

    assert 'Status: fail' in markdown
    assert '## FAIL: demo' in markdown
    assert "- selected_skill: demo_skill" in markdown
    assert "- error: bad contract" in markdown
