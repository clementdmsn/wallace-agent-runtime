from __future__ import annotations

from types import SimpleNamespace

from agent import agent as agent_module
from agent.model_streaming import fallback_tool_call_id


def seed_messages(wallace, user_content: str) -> None:
    wallace.messages = [
        {'role': 'system', 'content': 'base prompt'},
        {'role': 'user', 'content': user_content},
    ]


def test_call_model_selects_skill_and_builds_request_prompt(monkeypatch):
    selected = {
        'status': 'ok',
        'skill_name': 'demo_skill',
        'procedure': 'Follow the demo procedure.',
        'allowed_tools': ['read_file'],
        'forbidden_tool_calls': [],
        'recommended_tool_calls': [],
        'procedure_overrides': [],
        'selection': {'skill_name': 'demo_skill'},
    }
    events = []

    monkeypatch.setattr(agent_module, 'request_skill_for_intent', lambda text: selected)
    monkeypatch.setattr(agent_module, 'record_skill_event', lambda *args: events.append(args))

    wallace = agent_module.Agent()
    seed_messages(wallace, 'Use the demo skill')

    def fake_call_model_once(run_id):
        assert wallace.active_skill_name == 'demo_skill'
        assert wallace.active_skill_policy['allowed_tools'] == ['read_file']
        assert wallace.request_system_prompt is not None
        assert '# TASK-SPECIFIC PROCEDURE' in wallace.request_system_prompt
        assert 'Follow the demo procedure.' in wallace.request_system_prompt
        assert wallace.messages[0]['content'] == 'base prompt'
        return {'role': 'assistant', 'content': 'done'}

    monkeypatch.setattr(wallace, '_call_model_once', fake_call_model_once)

    assert wallace.call_model() == 'done'
    assert ('demo_skill', 'fulfilled') in events


def test_call_model_leaves_prompt_clean_when_no_skill(monkeypatch):
    monkeypatch.setattr(
        agent_module,
        'request_skill_for_intent',
        lambda text: {
            'status': 'ok',
            'skill_name': None,
            'selection': {'selection_reason': 'best skill below threshold'},
        },
    )

    wallace = agent_module.Agent()
    seed_messages(wallace, 'Plain question')

    def fake_call_model_once(run_id):
        assert wallace.active_skill_name is None
        assert wallace.request_system_prompt == 'base prompt'
        return {'role': 'assistant', 'content': 'plain answer'}

    monkeypatch.setattr(wallace, '_call_model_once', fake_call_model_once)

    assert wallace.call_model() == 'plain answer'


def test_followup_review_carries_prior_owasp_skill_context(monkeypatch):
    seen_texts = []

    def fake_request_skill(text):
        seen_texts.append(text)
        return {'status': 'ok', 'skill_name': None, 'selection': {}}

    monkeypatch.setattr(agent_module, 'request_skill_for_intent', fake_request_skill)

    wallace = agent_module.Agent()
    seed_messages(wallace, 'now review security_medium.py')
    wallace.last_fulfilled_skill_name = 'owasp_security_review'
    monkeypatch.setattr(wallace, '_call_model_once', lambda run_id: {'role': 'assistant', 'content': 'ok'})

    assert wallace.call_model() == 'ok'
    assert seen_texts == ['OWASP security review security_medium.py']


def test_streamed_tool_call_without_backend_id_gets_stable_fallback_id():
    wallace = agent_module.Agent()
    seed_messages(wallace, 'Read a file')
    run_id = wallace.reserve_generation()
    assert run_id is not None

    class FakeCompletions:
        def create(self, **kwargs):
            return [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content=None,
                                tool_calls=[
                                    SimpleNamespace(
                                        index=0,
                                        id=None,
                                        type='function',
                                        function=SimpleNamespace(
                                            name='read_file',
                                            arguments='{"path": "README.md"}',
                                        ),
                                    )
                                ],
                            )
                        )
                    ]
                )
            ]

    wallace.client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )

    response = wallace._call_model_once(run_id)

    assert response is not None
    tool_call = response['tool_calls'][0]
    assert tool_call['id'] == fallback_tool_call_id(run_id, 0, 0)
    assert wallace.messages[-1]['tool_calls'][0]['id'] == tool_call['id']


def test_streamed_tool_call_chunks_are_assembled_by_index():
    wallace = agent_module.Agent()
    seed_messages(wallace, 'Read a file')
    run_id = wallace.reserve_generation()
    assert run_id is not None

    class FakeCompletions:
        def create(self, **kwargs):
            return [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content=None,
                                tool_calls=[
                                    SimpleNamespace(
                                        index=0,
                                        id='call-read',
                                        type='function',
                                        function=SimpleNamespace(
                                            name='read_file',
                                            arguments='{"path":',
                                        ),
                                    )
                                ],
                            )
                        )
                    ]
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content=None,
                                tool_calls=[
                                    SimpleNamespace(
                                        index=0,
                                        id=None,
                                        type=None,
                                        function=SimpleNamespace(
                                            name=None,
                                            arguments=' "README.md"}',
                                        ),
                                    )
                                ],
                            )
                        )
                    ]
                ),
            ]

    wallace.client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )

    response = wallace._call_model_once(run_id)

    assert response is not None
    assert response['tool_calls'] == [
        {
            'id': 'call-read',
            'type': 'function',
            'function': {'name': 'read_file', 'arguments': '{"path": "README.md"}'},
        }
    ]
