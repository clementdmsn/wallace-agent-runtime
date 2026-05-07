from __future__ import annotations

import json

import sandbox
import tools.skill_authoring_tools as skill_authoring_tools
from tests.conftest import settings_for_sandbox
from tools.skill_authoring_tools import create_skill, finalize_skill_draft, repair_skill_draft


def valid_payload() -> dict[str, object]:
    return {
        'name': 'demo_skill',
        'summary': 'Create a demo skill.',
        'description': 'Create a demo skill for tests.',
        'categories': ['skills'],
        'when_to_use': ['When a demo skill is needed.'],
        'when_not_to_use': ['When no skill should be created.'],
        'trigger_actions': ['create demo skill'],
        'inputs': {},
        'outputs': {},
        'tools_required': [],
        'examples': ['Create a demo skill.'],
    }


def test_create_skill_rejects_missing_metadata_fields():
    payload = valid_payload()
    del payload['categories']

    result = create_skill('demo', '1. Do the task.', payload)

    assert result['status'] == 'error'
    assert result['error'] == 'json_payload missing required skill metadata fields'
    assert result['missing_fields'] == ['categories']


def test_create_skill_rejects_unknown_metadata_fields():
    payload = valid_payload()
    payload['unknown'] = True

    result = create_skill('demo', '1. Do the task.', payload)

    assert result['status'] == 'error'
    assert result['error'] == 'json_payload contains unknown skill metadata fields'
    assert result['unexpected_fields'] == ['unknown']


def test_create_skill_normalizes_question_shaped_triggers(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_authoring_tools, 'SETTINGS', settings)
    monkeypatch.setattr(
        skill_authoring_tools,
        'create_skill_faiss_index',
        lambda *args, **kwargs: {'status': 'ok'},
    )
    payload = valid_payload()
    payload['trigger_actions'] = ['what does this do?']

    result = create_skill('demo_question', '1. Do the task.', payload, rebuild_index=False)

    assert result['status'] == 'ok'
    assert result['metadata_path'] == 'skill_catalog/metadatas/demo_question.json'
    assert result['normalizations'][0]['field'] == 'trigger_actions'


def test_create_skill_rejects_unknown_input_names():
    payload = valid_payload()
    payload['inputs'] = {'file_path': {'type': 'string'}}

    result = create_skill('demo', '1. Do the task.', payload)

    assert result['status'] == 'error'
    assert result['error'] == 'json_payload failed skill quality validation'
    assert result['validation_errors'][0]['field'] == 'inputs'
    assert result['validation_errors'][0]['value']['unknown_inputs'] == ['file_path']
    assert result['repair_suggestions'][0] == {
        'field': 'inputs',
        'replace': 'file_path',
        'with': 'path',
        'reason': 'File paths must use the runtime input key path.',
    }


def test_create_skill_suggests_symbol_for_function_skill():
    payload = valid_payload()
    payload['name'] = 'debug_function'
    payload['inputs'] = {'function_path': {'type': 'string'}}

    result = create_skill('debug_function', '1. Do the task.', payload)

    assert result['status'] == 'error'
    assert {
        'field': 'inputs',
        'add': 'symbol',
        'schema': {
            'type': 'string',
            'description': 'Function or method name to inspect.',
        },
        'reason': 'Function-level skills should use symbol for the function name.',
    } in result['repair_suggestions']


def test_create_skill_normalizes_bare_string_input_and_output_schemas(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_authoring_tools, 'SETTINGS', settings)
    monkeypatch.setattr(
        skill_authoring_tools,
        'create_skill_faiss_index',
        lambda *args, **kwargs: {'status': 'ok'},
    )
    payload = valid_payload()
    payload['inputs'] = {'path': 'string'}
    payload['outputs'] = {'summary': 'string'}
    payload['examples'] = ['Create a demo skill for ./demo_project']

    result = create_skill('demo_schema', '1. Do the task.', payload, rebuild_index=False)

    assert result['status'] == 'ok'
    assert result['metadata_path'] == 'skill_catalog/metadatas/demo_schema.json'
    assert result['normalizations'][0]['field'] == 'inputs'
    assert result['normalizations'][1]['field'] == 'outputs'


def test_create_skill_requires_required_tools_in_markdown():
    payload = valid_payload()
    payload['tools_required'] = ['find_file']

    result = create_skill('demo', '1. Locate the target.', payload)

    assert result['status'] == 'error'
    assert result['error'] == 'json_payload failed skill quality validation'
    assert result['validation_errors'][0]['field'] == 'markdown'
    assert result['repair_instructions'] == [
        'Mention every required tool by exact name and include fallback/failure behavior.'
    ]


def test_create_skill_rejects_high_default_score_for_non_authoring_skill():
    payload = valid_payload()
    payload['categories'] = ['code_analysis']
    payload['when_not_to_use'] = ['Do not use for create edit refactor fix debug review test tasks.']
    payload['default_score'] = 0.95

    result = create_skill('demo', '1. Do the task.', payload)

    assert result['status'] == 'error'
    assert result['error'] == 'json_payload failed skill quality validation'
    assert result['validation_errors'][0]['field'] == 'default_score'


def test_create_skill_normalizes_code_skill_false_positive_exclusions(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_authoring_tools, 'SETTINGS', settings)
    monkeypatch.setattr(
        skill_authoring_tools,
        'create_skill_faiss_index',
        lambda *args, **kwargs: {'status': 'ok'},
    )
    payload = valid_payload()
    payload['categories'] = ['code_analysis']
    payload['trigger_actions'] = ['analyze code structure']
    payload['when_to_use'] = ['Use when analyzing code structure.']
    payload['default_score'] = 0.5
    payload['when_not_to_use'] = ['Do not use for unrelated tasks.']

    result = create_skill('demo_code_exclusions', '1. Do the task.', payload, rebuild_index=False)

    assert result['status'] == 'ok'
    assert result['normalizations'][0] == {
        'field': 'exclusions',
        'action': 'added_missing_code_task_false_positives',
        'added': ['create', 'edit', 'refactor', 'fix', 'debug', 'review', 'test'],
    }


def test_create_skill_rejects_required_path_when_examples_do_not_extract_it():
    payload = valid_payload()
    payload['categories'] = ['code_analysis']
    payload['trigger_actions'] = ['analyze codebase structure']
    payload['when_to_use'] = ['Use when analyzing codebase structure.']
    payload['when_not_to_use'] = ['Do not use for create edit refactor fix debug review test tasks.']
    payload['inputs'] = {'path': {'type': 'string', 'description': 'Codebase root path.'}}
    payload['examples'] = ['analyze the structure of snake_game']
    payload['default_score'] = 0.5

    result = create_skill('demo_path_probe', '1. Do the task.', payload)

    assert result['status'] == 'error'
    assert result['error'] == 'json_payload failed skill quality validation'
    assert result['validation_errors'][0]['field'] == 'examples'
    assert result['validation_errors'][0]['value']['missing_runtime_args'] == ['path']
    assert './snake_game' in result['repair_instructions'][0]
    assert result['repair_suggestions'][0]['field'] == 'examples'
    assert result['repair_suggestions'][0]['set'] == ['analyze the structure of snake_game at ./example_project']


def test_create_skill_accepts_required_path_when_example_extracts_it(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_authoring_tools, 'SETTINGS', settings)
    monkeypatch.setattr(
        skill_authoring_tools,
        'create_skill_faiss_index',
        lambda *args, **kwargs: {'status': 'ok'},
    )
    payload = valid_payload()
    payload['categories'] = ['code_analysis']
    payload['trigger_actions'] = ['analyze codebase structure']
    payload['when_to_use'] = ['Use when analyzing codebase structure.']
    payload['when_not_to_use'] = ['Do not use for create edit refactor fix debug review test tasks.']
    payload['inputs'] = {'path': {'type': 'string', 'description': 'Codebase root path.'}}
    payload['examples'] = ['analyze the structure of ./snake_game']
    payload['default_score'] = 0.5

    result = create_skill('demo_path_probe_ok', '1. Do the task.', payload, rebuild_index=False)

    assert result['status'] == 'ok'
    assert result['metadata_path'] == 'skill_catalog/metadatas/demo_path_probe_ok.json'


def test_validate_skill_payload_requires_code_exclusions_in_metadata_not_markdown_only():
    payload = valid_payload()
    payload['categories'] = ['code_analysis']
    payload['trigger_actions'] = ['analyze code structure']
    payload['when_to_use'] = ['Use when analyzing code structure.']
    payload['default_score'] = 0.5
    payload['when_not_to_use'] = [
        'Do not use for debug tasks.',
        'Do not use for code review.',
        'Do not use for test tasks.',
        'Do not use for fix tasks.',
    ]
    markdown = '1. Do the task.\n2. Do not use for create, edit, or refactor tasks.'

    errors = skill_authoring_tools.validate_skill_payload(markdown, payload)

    assert errors[0] == {
        'field': 'when_not_to_use',
        'message': 'code skills must exclude nearby code task types they do not handle',
        'value': {'missing_exclusions': ['create', 'edit', 'refactor']},
    }
    instructions = skill_authoring_tools.build_repair_instructions(errors)
    assert 'create, edit, refactor' in instructions[0]
    assert 'not only the markdown procedure' in instructions[0]


def test_repair_skill_draft_applies_structured_metadata_repairs(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_authoring_tools, 'SETTINGS', settings)
    monkeypatch.setattr(
        skill_authoring_tools,
        'create_skill_faiss_index',
        lambda *args, **kwargs: {'status': 'ok'},
    )

    payload = valid_payload()
    del payload['examples']
    payload['trigger_actions'] = ['what does this do?']

    draft = skill_authoring_tools.validation_failure_result(
        [
            {
                'field': 'examples',
                'message': 'must include at least one example request',
            },
            {
                'field': 'routing_text',
                'message': 'routing examples and trigger text must be instruction-style, not question-shaped',
                'value': [{'field': 'trigger_actions', 'text': 'what does this do?'}],
            },
        ],
        '1. Do the task.',
        payload,
        'demo_finalize',
    )
    assert draft['status'] == 'error'

    repair = repair_skill_draft('demo_finalize', draft['repair_suggestions'])
    assert repair['status'] == 'ok'
    assert repair['message'] == 'skill draft repaired; call finalize_skill_draft next'

    result = finalize_skill_draft('demo_finalize', rebuild_index=False)

    assert result['status'] == 'ok'
    assert result['metadata_path'] == 'skill_catalog/metadatas/demo_finalize.json'
    assert result['procedure_path'] == 'skill_catalog/procedures/demo_finalize.md'


def test_create_skill_rejects_invalid_top_level_inputs():
    assert create_skill('', '1. Do the task.', valid_payload()) == {
        'status': 'error',
        'error': 'title must be a non-empty string',
    }
    assert create_skill('demo', '', valid_payload()) == {
        'status': 'error',
        'error': 'markdown must be a non-empty string',
    }
    assert create_skill('demo', '1. Do the task.', []) == {
        'status': 'error',
        'error': 'json_payload must be an object',
    }


def test_create_skill_rejects_duplicate_existing_skill(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_authoring_tools, 'SETTINGS', settings)
    monkeypatch.setattr(
        skill_authoring_tools,
        'create_skill_faiss_index',
        lambda *args, **kwargs: {'status': 'ok'},
    )
    first = create_skill('duplicate', '1. Do the task.', valid_payload(), rebuild_index=False)
    second = create_skill('duplicate', '1. Do the task.', valid_payload(), rebuild_index=False)

    assert first['status'] == 'ok'
    assert second['status'] == 'error'
    assert second['error'] == 'skill already exists'


def test_create_skill_reports_index_update_failure(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_authoring_tools, 'SETTINGS', settings)
    monkeypatch.setattr(
        skill_authoring_tools,
        'create_skill_faiss_index',
        lambda *args, **kwargs: {'status': 'error', 'error': 'embedding unavailable'},
    )

    result = create_skill('index_fail', '1. Do the task.', valid_payload(), rebuild_index=False)

    assert result['status'] == 'error'
    assert result['error'] == 'skill files were written, but index update failed'
    assert result['index_result']['error'] == 'embedding unavailable'


def test_create_skill_reports_registry_reload_failure(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_authoring_tools, 'SETTINGS', settings)
    monkeypatch.setattr(
        skill_authoring_tools,
        'create_skill_faiss_index',
        lambda *args, **kwargs: {'status': 'ok'},
    )

    from skills import skills as skills_module

    monkeypatch.setattr(
        skills_module,
        'refresh_skill_registry',
        lambda: (_ for _ in ()).throw(RuntimeError('reload failed')),
    )

    result = create_skill('reload_fail', '1. Do the task.', valid_payload(), rebuild_index=False)

    assert result['status'] == 'ok'
    assert result['registry_reloaded'] is False
    assert result['registry_reload_error'] == 'reload failed'


def test_finalize_skill_draft_reports_missing_and_invalid_drafts(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_authoring_tools, 'SETTINGS', settings)

    missing = finalize_skill_draft('missing')
    assert missing['status'] == 'error'
    assert missing['error'] == 'skill draft not found'

    draft_dir = tmp_path / 'skills' / 'drafts'
    draft_dir.mkdir(parents=True)
    (draft_dir / 'bad_json.json').write_text('{', encoding='utf-8')
    (draft_dir / 'bad_json.md').write_text('1. Do the task.', encoding='utf-8')
    bad_json = finalize_skill_draft('bad_json')
    assert bad_json['status'] == 'error'
    assert bad_json['error'].startswith('invalid draft metadata JSON:')

    (draft_dir / 'bad_type.json').write_text('[]', encoding='utf-8')
    (draft_dir / 'bad_type.md').write_text('1. Do the task.', encoding='utf-8')
    bad_type = finalize_skill_draft('bad_type')
    assert bad_type == {
        'status': 'error',
        'error': 'draft metadata JSON must be an object',
        'draft_id': 'bad_type',
    }


def test_repair_skill_draft_reports_input_errors(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_authoring_tools, 'SETTINGS', settings)

    assert repair_skill_draft('', []) == {
        'status': 'error',
        'error': 'draft_id must be a non-empty string',
    }
    assert repair_skill_draft('demo', {}) == {
        'status': 'error',
        'error': 'repairs must be an array',
    }
    assert repair_skill_draft('missing', []) == {
        'status': 'error',
        'error': 'skill draft not found',
        'draft_id': 'missing',
    }


def test_repair_skill_draft_reports_invalid_json_and_metadata_errors(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_authoring_tools, 'SETTINGS', settings)

    draft_dir = tmp_path / 'skills' / 'drafts'
    draft_dir.mkdir(parents=True)
    (draft_dir / 'invalid_json.json').write_text('{', encoding='utf-8')
    (draft_dir / 'invalid_json.md').write_text('1. Do the task.', encoding='utf-8')

    invalid = repair_skill_draft('invalid_json', [])

    assert invalid['status'] == 'error'
    assert invalid['error'].startswith('invalid draft metadata JSON:')

    payload = valid_payload()
    del payload['categories']
    (draft_dir / 'missing_field.json').write_text(json.dumps(payload), encoding='utf-8')
    (draft_dir / 'missing_field.md').write_text('1. Do the task.', encoding='utf-8')

    missing = repair_skill_draft('missing_field', [])

    assert missing['status'] == 'error'
    assert missing['error'] == 'json_payload missing required skill metadata fields'
    assert missing['applied_repairs'] == []
    assert missing['draft_metadata_path'] == 'skills/drafts/missing_field.json'
