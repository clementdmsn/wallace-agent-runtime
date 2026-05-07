from system_prompt.system_prompt import (
    CONSTITUTION,
    PROMPT_DIR,
    build_request_system_prompt,
    build_system_prompt,
)


def test_build_system_prompt_separates_fragments():
    prompt = build_system_prompt()
    fragments = [
        (PROMPT_DIR / file).read_text(encoding='utf-8').strip()
        for file in CONSTITUTION
    ]

    assert prompt == '\n\n'.join(fragments)
    assert 'task-specific procedure is included' in prompt
    assert 'deprecation alone is not a reason to skip' in prompt
    assert 'request_skill_for_intent' not in prompt


def test_build_request_system_prompt_returns_base_when_no_skill():
    assert build_request_system_prompt('base prompt', None) == 'base prompt'


def test_build_request_system_prompt_injects_selected_skill_procedure():
    prompt = build_request_system_prompt(
        'base prompt',
        {
            'skill_name': 'demo_skill',
            'procedure': '1. Inspect the target.\n2. Answer from evidence.',
            'procedure_overrides': ['Call the listed tool first.'],
            'recommended_tool_calls': [
                {
                    'tool': 'summarize_code_file',
                    'arguments': {'path': 'app.py'},
                    'reason': 'Whole-file overview.',
                }
            ],
            'allowed_tools': ['summarize_code_file'],
            'forbidden_tool_calls': [
                {'tool': 'read_file', 'reason': 'Use the code overview tool.'}
            ],
        },
    )

    assert prompt.startswith('base prompt\n\n# TASK-SPECIFIC PROCEDURE')
    assert 'Selected skill: demo_skill' in prompt
    assert 'Call the listed tool first.' in prompt
    assert 'summarize_code_file' in prompt
    assert 'read_file: Use the code overview tool.' in prompt
    assert '1. Inspect the target.' in prompt
