from __future__ import annotations

from skills import selection, skills
from skills.skills_registry import Skill


def security_review_skill() -> Skill:
    return Skill(
        name='owasp_security_review',
        description='Review code for security issues using OWASP references.',
        implementation_name='owasp_security_review',
        parameters={
            'type': 'object',
            'properties': {'path': {'type': 'string'}},
            'required': ['path'],
            'additionalProperties': False,
        },
        category='code',
        tags=frozenset({'owasp', 'security', 'audit', 'review', 'code', 'python'}),
        supported_actions=frozenset({'review'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
        required_args=frozenset({'path'}),
        tools_required=('discover_review_targets', 'search_owasp_reference'),
        default_score=0.7,
    )


def test_choose_skill_returns_null_selection_when_no_candidates(monkeypatch):
    monkeypatch.setattr(selection, 'retrieve_skill_candidates', lambda *args, **kwargs: [])

    result = selection.choose_skill_for_intent({}, 'Explain something', {})

    assert result['status'] == 'ok'
    assert result['skill_name'] is None
    assert result['selection_reason'] == 'no relevant skill candidates found'
    assert result['candidates'] == []


def test_choose_skill_returns_null_selection_when_best_score_is_below_threshold(monkeypatch):
    skill = Skill(
        name='low_score',
        description='Low scoring skill.',
        implementation_name='low_score',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        default_score=0.0,
    )

    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [(skill, {'distance': 0.1})],
    )

    result = selection.choose_skill_for_intent({}, 'Unrelated task', {}, threshold=100.0)

    assert result['status'] == 'ok'
    assert result['skill_name'] is None
    assert result['selection_reason'] == 'best skill below threshold'
    assert result['best_candidate']['skill_name'] == 'low_score'


def test_create_extensionless_file_does_not_select_skill_authoring_skill(monkeypatch):
    create_skill = Skill(
        name='create_new_skill',
        description='Create a new reusable skill.',
        implementation_name='create_new_skill',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        category='skills',
        tags=frozenset({'create', 'skill', 'reusable'}),
        supported_actions=frozenset({'create'}),
        supported_domains=frozenset({'skills'}),
        default_score=0.9,
    )
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [(create_skill, {'distance': 0.1})],
    )

    result = selection.choose_skill_for_intent(
        {},
        'create a file named aaa',
        {},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] is None
    assert result['selection_reason'] == 'no skill candidates passed validation'
    assert result['rejected_candidates'][0]['skill_name'] == 'create_new_skill'
    assert result['rejected_candidates'][0]['rejection_reason'] == 'missing explicit skill-authoring intent'


def test_request_skill_for_intent_returns_null_selection_without_loading_skill(monkeypatch):
    monkeypatch.setattr(
        skills,
        'choose_skill_for_intent',
        lambda *args, **kwargs: {
            'status': 'ok',
            'skill_name': None,
            'message': 'No relevant skill is available.',
        },
    )

    result = skills.request_skill_for_intent('Do something unusual')

    assert result == {
        'status': 'ok',
        'skill_name': None,
        'arguments': {},
        'selection': {
            'status': 'ok',
            'skill_name': None,
            'message': 'No relevant skill is available.',
        },
        'message': 'No relevant skill is available.',
    }


def test_review_intent_prefers_review_skill_over_file_explanation(monkeypatch):
    review_skill = Skill(
        name='review_code_quality',
        description='Review code quality.',
        implementation_name='review_code_quality',
        parameters={
            'type': 'object',
            'properties': {'path': {'type': 'string'}},
            'required': ['path'],
            'additionalProperties': False,
        },
        category='code',
        tags=frozenset({'review', 'code', 'quality', 'python'}),
        supported_actions=frozenset({'review'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
        required_args=frozenset({'path'}),
        default_score=0.5,
    )
    explain_skill = Skill(
        name='skill_explain_file',
        description='Explain a code file.',
        implementation_name='skill_explain_file',
        parameters={
            'type': 'object',
            'properties': {'path': {'type': 'string'}},
            'required': ['path'],
            'additionalProperties': False,
        },
        category='code',
        tags=frozenset({'explain', 'file', 'python'}),
        supported_actions=frozenset({'summarize'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
        required_args=frozenset({'path'}),
        default_score=0.9,
    )
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [
            (explain_skill, {'distance': 0.1}),
            (review_skill, {'distance': 0.2}),
        ],
    )

    result = selection.choose_skill_for_intent(
        {},
        'Review review_target.py',
        {'path': 'review_target.py'},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] == 'review_code_quality'


def test_security_audit_intent_prefers_owasp_security_review(monkeypatch):
    security_skill = security_review_skill()
    quality_skill = Skill(
        name='review_code_quality',
        description='Review code quality.',
        implementation_name='review_code_quality',
        parameters={
            'type': 'object',
            'properties': {'path': {'type': 'string'}},
            'required': ['path'],
            'additionalProperties': False,
        },
        category='code',
        tags=frozenset({'review', 'code', 'quality', 'python'}),
        supported_actions=frozenset({'review'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
        required_args=frozenset({'path'}),
        default_score=0.5,
    )
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [
            (quality_skill, {'distance': 0.1}),
            (security_skill, {'distance': 0.2}),
        ],
    )

    result = selection.choose_skill_for_intent(
        {'owasp_security_review': security_skill, 'review_code_quality': quality_skill},
        'Security audit app.py using OWASP',
        {'path': 'app.py'},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] == 'owasp_security_review'
    assert result['forced'] is True


def test_security_audit_forces_owasp_skill_without_retrieval(monkeypatch):
    def fail_retrieval(*args, **kwargs):
        raise AssertionError('forced OWASP audit selection should not call retrieval')

    monkeypatch.setattr(selection, 'retrieve_skill_candidates', fail_retrieval)

    result = selection.choose_skill_for_intent(
        {'owasp_security_review': security_review_skill()},
        'audit app.py for vulnerabilities',
        {'path': 'app.py'},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] == 'owasp_security_review'
    assert result['forced'] is True
    assert 'forced_owasp_security_audit_intent' in result['validation']['reasons']


def test_security_audit_missing_path_does_not_fall_back_to_quality_review(monkeypatch):
    quality_skill = Skill(
        name='review_code_quality',
        description='Review code quality.',
        implementation_name='review_code_quality',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        category='code',
        tags=frozenset({'review', 'code', 'quality'}),
        supported_actions=frozenset({'review'}),
        supported_domains=frozenset({'code'}),
        default_score=0.9,
    )
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [(quality_skill, {'distance': 0.1})],
    )

    result = selection.choose_skill_for_intent(
        {'owasp_security_review': security_review_skill(), 'review_code_quality': quality_skill},
        'security audit the code for OWASP issues',
        {},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] is None
    assert result['selection_reason'] == 'owasp security audit requested but required arguments are missing'


def test_forced_owasp_security_review_reports_missing_skill():
    result = selection.choose_skill_for_intent(
        {},
        'security audit app.py using OWASP',
        {'path': 'app.py'},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] is None
    assert result['selection_reason'] == 'owasp security audit requested but owasp_security_review is not loaded'


def test_explicit_owasp_security_audit_rejects_fix_requests():
    intent = selection.extract_intent('fix app.py security bug')

    assert selection.is_explicit_owasp_security_audit_intent(intent) is False


def test_skill_has_lexical_trigger_variants():
    skill_authoring = Skill(
        name='create_skill',
        description='Create skills.',
        implementation_name='create_skill',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        category='skills',
        tags=frozenset({'skill', 'create'}),
    )
    code_skill = Skill(
        name='explain_python',
        description='Explain Python code.',
        implementation_name='explain_python',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        category='code',
        tags=frozenset({'explain', 'python'}),
        supported_actions=frozenset({'summarize'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
    )

    assert selection.skill_has_lexical_trigger(
        skill_authoring,
        selection.extract_intent('create a reusable skill'),
    ) is True
    assert selection.skill_has_lexical_trigger(
        code_skill,
        selection.extract_intent('summarize app.py'),
    ) is True
    assert selection.skill_has_lexical_trigger(
        code_skill,
        selection.extract_intent('explain python module app.py'),
    ) is True
    assert selection.skill_has_lexical_trigger(
        code_skill,
        selection.extract_intent('cook dinner'),
    ) is False


def test_validate_skill_syntax_rejects_unexpected_and_wrong_typed_args():
    skill = Skill(
        name='strict',
        description='Strict skill.',
        implementation_name='strict',
        parameters={
            'type': 'object',
            'properties': {'path': {'type': 'string'}},
            'required': ['path'],
            'additionalProperties': False,
        },
    )

    assert selection.validate_skill_syntax(skill, {}) == (False, 'missing required argument(s): path')
    assert selection.validate_skill_syntax(skill, {'path': 'app.py', 'extra': 'x'}) == (
        False,
        'unexpected arguments: extra',
    )
    assert selection.validate_skill_syntax(skill, {'path': 123}) == (
        False,
        "argument 'path' must be a string",
    )


def test_score_skill_choice_covers_question_domain_filetype_and_history(monkeypatch):
    skill = Skill(
        name='question_skill',
        description='Explain Python files.',
        implementation_name='question_skill',
        parameters={'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']},
        category='code',
        tags=frozenset({'explain', 'python'}),
        supported_actions=frozenset({'summarize'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
        required_args=frozenset({'path'}),
        default_score=0.5,
        priority=10,
        specificity=5,
    )
    monkeypatch.setattr(selection, 'get_skill_score_bonus', lambda name: 1.25)

    score, validation = selection.score_skill_choice(skill, 'What does app.py do?', {'path': 'app.py'})

    assert score > 0
    assert 'question_penalty' in validation['reasons']
    assert 'domain_match' in validation['reasons']
    assert 'filetype_match' in validation['reasons']
    assert 'required_args_present' in validation['reasons']
    assert 'history_bonus=1.25' in validation['reasons']


def test_score_skill_choice_penalizes_mixed_question_and_action_mismatch(monkeypatch):
    skill = Skill(
        name='edit_skill',
        description='Edit code.',
        implementation_name='edit_skill',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        category='code',
        tags=frozenset({'code'}),
        supported_actions=frozenset({'edit'}),
    )
    monkeypatch.setattr(
        selection,
        'extract_intent',
        lambda text: {
            'tokens': {'review', 'code'},
            'action': 'review',
            'domain': 'code',
            'filetype': 'py',
            'speech_act': 'mixed',
            'args': {'path': 'app.py'},
        },
    )

    score, validation = selection.score_skill_choice(
        skill,
        'Can you review app.py and explain it',
        {'path': 'app.py'},
    )

    assert score < 0
    assert 'mixed_question_penalty' in validation['reasons']
    assert 'action_mismatch' in validation['reasons']


def test_build_retrieval_query_includes_intent_and_target_details():
    query = selection.build_retrieval_query(
        'Explain function login in auth.py',
        {'path': 'auth.py', 'symbol': 'login'},
    )

    assert 'action: summarize' in query
    assert 'domain: code' in query
    assert 'target filetype: py' in query
    assert 'target is a sandbox file path' in query
    assert 'target includes a specific symbol or method' in query


def test_retrieve_skill_candidates_skips_faiss_when_no_lexical_trigger(monkeypatch):
    skill = Skill(
        name='code_skill',
        description='Explain code.',
        implementation_name='code_skill',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        tags=frozenset({'python', 'explain'}),
    )
    monkeypatch.setattr(
        selection,
        'search_skill_faiss_index',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('FAISS should not be called')),
    )

    assert selection.retrieve_skill_candidates({'code_skill': skill}, 'cook dinner', {}) == []


def test_retrieve_skill_candidates_groups_best_distance_and_skips_unknown(monkeypatch):
    skill = Skill(
        name='code_skill',
        description='Explain code.',
        implementation_name='code_skill',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        tags=frozenset({'explain', 'python'}),
        supported_actions=frozenset({'summarize'}),
    )
    monkeypatch.setattr(
        selection,
        'search_skill_faiss_index',
        lambda query, k: {
            'status': 'ok',
            'matches': [
                {'skill_name': 'code_skill', 'distance': 0.8},
                {'skill_name': 'missing', 'distance': 0.1},
                {'skill_name': 'code_skill', 'distance': 0.2},
                {'distance': 0.0},
            ],
        },
    )
    events = []
    monkeypatch.setattr(selection, 'record_skill_event', lambda name, event: events.append((name, event)))

    result = selection.retrieve_skill_candidates(
        {'code_skill': skill},
        'explain python file',
        {},
    )

    assert result == [(skill, {'skill_name': 'code_skill', 'distance': 0.2})]
    assert events == [('code_skill', 'retrieved')]


def test_retrieve_skill_candidates_returns_empty_when_faiss_errors(monkeypatch):
    skill = Skill(
        name='code_skill',
        description='Explain code.',
        implementation_name='code_skill',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        tags=frozenset({'explain', 'python'}),
        supported_actions=frozenset({'summarize'}),
    )
    monkeypatch.setattr(selection, 'search_skill_faiss_index', lambda query, k: {'status': 'error'})

    assert selection.retrieve_skill_candidates({'code_skill': skill}, 'explain python file', {}) == []


def test_choose_skill_records_selected_event(monkeypatch):
    skill = Skill(
        name='explain_skill',
        description='Explain code.',
        implementation_name='explain_skill',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        tags=frozenset({'explain', 'python'}),
        supported_actions=frozenset({'summarize'}),
        default_score=1.0,
    )
    events = []
    monkeypatch.setattr(selection, 'retrieve_skill_candidates', lambda *args, **kwargs: [(skill, {'distance': 0.4})])
    monkeypatch.setattr(selection, 'record_skill_event', lambda name, event: events.append((name, event)))

    result = selection.choose_skill_for_intent({}, 'explain python code', {})

    assert result['skill_name'] == 'explain_skill'
    assert events == [('explain_skill', 'selected')]


def test_fix_security_issue_does_not_force_owasp_audit(monkeypatch):
    quality_skill = Skill(
        name='review_code_quality',
        description='Review code quality.',
        implementation_name='review_code_quality',
        parameters={
            'type': 'object',
            'properties': {'path': {'type': 'string'}},
            'required': ['path'],
            'additionalProperties': False,
        },
        category='code',
        tags=frozenset({'review', 'code', 'quality', 'python'}),
        supported_actions=frozenset({'review'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
        required_args=frozenset({'path'}),
        default_score=0.5,
    )
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [(quality_skill, {'distance': 0.1})],
    )

    result = selection.choose_skill_for_intent(
        {'owasp_security_review': security_review_skill(), 'review_code_quality': quality_skill},
        'fix the security issue in app.py',
        {'path': 'app.py'},
    )

    assert result['status'] == 'ok'
    assert result.get('forced') is None
    assert result['skill_name'] != 'owasp_security_review'


def test_owasp_skill_is_rejected_without_explicit_security_audit_intent(monkeypatch):
    owasp_skill = security_review_skill()
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [(owasp_skill, {'distance': 0.1})],
    )

    result = selection.choose_skill_for_intent(
        {'owasp_security_review': owasp_skill},
        'review security_easy.py',
        {'path': 'security_easy.py'},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] is None
    assert result['selection_reason'] == 'no skill candidates passed validation'
    assert result['rejected_candidates'][0]['rejection_reason'] == 'missing explicit OWASP/security audit intent'


def test_question_intent_penalty_suppresses_skill_selection(monkeypatch):
    explain_skill = Skill(
        name='skill_explain_file',
        description='Explain a code file.',
        implementation_name='skill_explain_file',
        parameters={
            'type': 'object',
            'properties': {'path': {'type': 'string'}},
            'required': ['path'],
            'additionalProperties': False,
        },
        category='code',
        tags=frozenset({'explain', 'file', 'python'}),
        supported_actions=frozenset({'summarize'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
        required_args=frozenset({'path'}),
        default_score=0.5,
    )
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [(explain_skill, {'distance': 0.1})],
    )

    result = selection.choose_skill_for_intent(
        {},
        'What does auth.py do?',
        {'path': 'auth.py'},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] is None
    assert result['selection_reason'] == 'best skill below threshold'
    assert result['candidates'][0]['skill_name'] == 'skill_explain_file'


def test_command_intent_can_still_select_skill(monkeypatch):
    explain_skill = Skill(
        name='skill_explain_file',
        description='Explain a code file.',
        implementation_name='skill_explain_file',
        parameters={
            'type': 'object',
            'properties': {'path': {'type': 'string'}},
            'required': ['path'],
            'additionalProperties': False,
        },
        category='code',
        tags=frozenset({'explain', 'file', 'python'}),
        supported_actions=frozenset({'summarize'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
        required_args=frozenset({'path'}),
        default_score=0.5,
    )
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [(explain_skill, {'distance': 0.1})],
    )

    result = selection.choose_skill_for_intent(
        {},
        'Explain auth.py',
        {'path': 'auth.py'},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] == 'skill_explain_file'


def test_create_code_file_does_not_select_skill_authoring_skill(monkeypatch):
    create_skill = Skill(
        name='create_new_skill',
        description='Create a new reusable skill.',
        implementation_name='create_new_skill',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        category='skills',
        tags=frozenset({'create', 'skill', 'reusable'}),
        supported_actions=frozenset({'create'}),
        supported_domains=frozenset({'skills'}),
        default_score=0.9,
    )
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [(create_skill, {'distance': 0.1})],
    )

    result = selection.choose_skill_for_intent(
        {},
        'create a simple snake game in snake.py. I want a good object oriented architecture',
        {'path': 'snake.py'},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] is None
    assert result['selection_reason'] == 'no skill candidates passed validation'
    assert result['rejected_candidates'][0]['rejection_reason'] == 'missing explicit skill-authoring intent'


def test_explicit_skill_creation_still_selects_skill_authoring_skill(monkeypatch):
    create_skill = Skill(
        name='create_new_skill',
        description='Create a new reusable skill.',
        implementation_name='create_new_skill',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        category='skills',
        tags=frozenset({'create', 'skill', 'reusable'}),
        supported_actions=frozenset({'create'}),
        supported_domains=frozenset({'skills'}),
        default_score=0.9,
    )
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [(create_skill, {'distance': 0.1})],
    )

    result = selection.choose_skill_for_intent(
        {},
        'Create a skill for reviewing Python files',
        {},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] == 'create_new_skill'


def test_no_lexical_trigger_skips_retrieval(monkeypatch):
    skill = Skill(
        name='understand_python_file',
        description='Understand a Python file.',
        implementation_name='understand_python_file',
        parameters={'type': 'object', 'properties': {}, 'required': []},
        category='code_analysis',
        tags=frozenset({'understand', 'python', 'file'}),
        supported_actions=frozenset({'summarize'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
    )

    def fail_search(*args, **kwargs):
        raise AssertionError('retrieval should have been skipped')

    monkeypatch.setattr(selection, 'search_skill_faiss_index', fail_search)

    result = selection.choose_skill_for_intent(
        {'understand_python_file': skill},
        'you can search for it',
        {},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] is None
    assert result['selection_reason'] == 'no relevant skill candidates found'


def test_missing_required_args_rejects_candidate(monkeypatch):
    skill = Skill(
        name='understand_python_file',
        description='Understand a Python file.',
        implementation_name='understand_python_file',
        parameters={
            'type': 'object',
            'properties': {'path': {'type': 'string'}},
            'required': ['path'],
            'additionalProperties': False,
        },
        category='code_analysis',
        tags=frozenset({'understand', 'python', 'file'}),
        supported_actions=frozenset({'summarize'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
    )
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [(skill, {'distance': 0.1})],
    )

    result = selection.choose_skill_for_intent(
        {},
        'Explain this Python file',
        {},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] is None
    assert result['selection_reason'] == 'no skill candidates passed validation'
    assert result['rejected_candidates'][0]['skill_name'] == 'understand_python_file'


def test_action_mismatch_suppresses_analysis_skill_for_create_file_task(monkeypatch):
    skill = Skill(
        name='understand_python_file',
        description='Understand a Python file.',
        implementation_name='understand_python_file',
        parameters={
            'type': 'object',
            'properties': {'path': {'type': 'string'}},
            'required': ['path'],
            'additionalProperties': False,
        },
        category='code_analysis',
        tags=frozenset({'understand', 'python', 'file'}),
        supported_actions=frozenset({'summarize'}),
        supported_domains=frozenset({'code'}),
        supported_filetypes=frozenset({'py'}),
        required_args=frozenset({'path'}),
        default_score=0.55,
    )
    monkeypatch.setattr(
        selection,
        'retrieve_skill_candidates',
        lambda *args, **kwargs: [(skill, {'distance': 0.1})],
    )

    result = selection.choose_skill_for_intent(
        {},
        'create a simple snake game in snake.py',
        {'path': 'snake.py'},
    )

    assert result['status'] == 'ok'
    assert result['skill_name'] is None
    assert result['selection_reason'] == 'best skill below threshold'
    assert result['best_candidate']['skill_name'] == 'understand_python_file'
