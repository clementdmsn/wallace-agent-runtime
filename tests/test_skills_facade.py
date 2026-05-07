from __future__ import annotations

from skills import skills
from skills.skills_registry import Skill


def make_skill() -> Skill:
    return Skill(
        name='demo_skill',
        description='Demo skill.',
        implementation_name='demo_skill',
        parameters={'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']},
        procedure='Follow the demo procedure.',
        metadata_path='skills/metadatas/demo_skill.json',
        procedure_path='skills/procedures/demo_skill.md',
        when_to_use=('Use for demos.',),
        when_not_to_use=('Do not use for non-demos.',),
        exclusions=('non-demo',),
        preconditions=('A path is available.',),
        tools_required=('read_file',),
    )


def test_refresh_skill_registry_reloads_global_skill_map(monkeypatch):
    skill = make_skill()
    monkeypatch.setattr(skills, 'load_skills', lambda: [skill])

    skills.refresh_skill_registry()

    assert skills.SKILLS == [skill]
    assert skills.SKILLS_BY_NAME == {'demo_skill': skill}
    assert skills.get_skill('demo_skill') == skill


def test_facade_retrieve_and_choose_delegate_with_current_registry(monkeypatch):
    skill = make_skill()
    monkeypatch.setattr(skills, 'SKILLS_BY_NAME', {'demo_skill': skill})
    retrieved = []
    chosen = []
    monkeypatch.setattr(
        skills,
        '_retrieve_skill_candidates',
        lambda registry, user_text, arguments, k: retrieved.append((registry, user_text, arguments, k)) or [],
    )
    monkeypatch.setattr(
        skills,
        '_choose_skill_for_intent',
        lambda registry, user_text, arguments, k, threshold: chosen.append((registry, user_text, arguments, k, threshold)) or {'status': 'ok'},
    )

    assert skills.retrieve_skill_candidates('demo', {'path': 'a.py'}, k=3) == []
    assert skills.choose_skill_for_intent('demo', {'path': 'a.py'}, k=4, threshold=9.5) == {'status': 'ok'}

    assert retrieved == [({'demo_skill': skill}, 'demo', {'path': 'a.py'}, 3)]
    assert chosen == [({'demo_skill': skill}, 'demo', {'path': 'a.py'}, 4, 9.5)]


def test_request_skill_for_intent_rejects_bad_inputs():
    assert skills.request_skill_for_intent(123) == {'status': 'error', 'error': 'intent must be a string'}
    assert skills.request_skill_for_intent('   ') == {'status': 'error', 'error': 'empty intent'}
    assert skills.request_skill_for_intent('demo', []) == {'status': 'error', 'error': 'arguments must be an object'}


def test_request_skill_for_intent_returns_choice_error(monkeypatch):
    monkeypatch.setattr(skills, 'choose_skill_for_intent', lambda *args, **kwargs: {'status': 'error', 'error': 'boom'})

    assert skills.request_skill_for_intent('demo') == {'status': 'error', 'error': 'boom'}


def test_request_skill_for_intent_reports_unloaded_selected_skill(monkeypatch):
    monkeypatch.setattr(skills, 'SKILLS_BY_NAME', {})
    monkeypatch.setattr(
        skills,
        'choose_skill_for_intent',
        lambda *args, **kwargs: {'status': 'ok', 'skill_name': 'missing_skill'},
    )

    assert skills.request_skill_for_intent('demo') == {
        'status': 'error',
        'error': 'selected skill is not loaded: missing_skill',
    }


def test_request_skill_for_intent_returns_loaded_skill_guidance(monkeypatch):
    skill = make_skill()
    monkeypatch.setattr(skills, 'SKILLS_BY_NAME', {'demo_skill': skill})
    monkeypatch.setattr(
        skills,
        'choose_skill_for_intent',
        lambda intent, arguments, k, threshold: {'status': 'ok', 'skill_name': 'demo_skill', 'score': 10},
    )
    monkeypatch.setattr(
        skills,
        'build_execution_guidance',
        lambda skill, intent, arguments: {
            'resolved_task_type': 'demo',
            'recommended_tool_calls': [{'tool': 'read_file', 'arguments': {'path': arguments['path']}}],
            'allowed_tools': ['read_file'],
            'forbidden_tool_calls': [],
            'procedure_overrides': ['Read first.'],
        },
    )

    result = skills.request_skill_for_intent('demo ./app.py', {'path': 'app.py'})

    assert result['status'] == 'ok'
    assert result['skill_name'] == 'demo_skill'
    assert result['description'] == 'Demo skill.'
    assert result['procedure'] == 'Follow the demo procedure.'
    assert result['tools_required'] == ['read_file']
    assert result['preconditions'] == ['A path is available.']
    assert result['when_to_use'] == ['Use for demos.']
    assert result['when_not_to_use'] == ['Do not use for non-demos.']
    assert result['exclusions'] == ['non-demo']
    assert result['arguments'] == {'path': 'app.py'}
    assert result['resolved_task_type'] == 'demo'
    assert result['recommended_tool_calls'][0]['tool'] == 'read_file'
    assert result['allowed_tools'] == ['read_file']
    assert result['procedure_overrides'] == ['Read first.']
    assert result['selection'] == {'status': 'ok', 'skill_name': 'demo_skill', 'score': 10}
