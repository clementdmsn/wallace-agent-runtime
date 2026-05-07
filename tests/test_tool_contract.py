from __future__ import annotations

from sandbox import ALLOWED_COMMANDS
from tools.schemas import OPENAI_TOOLS
from tools.tools import TOOLS


def test_request_skill_for_intent_is_not_model_visible():
    exposed_names = {
        tool['function']['name']
        for tool in OPENAI_TOOLS
        if tool.get('type') == 'function'
    }

    assert 'request_skill_for_intent' not in exposed_names
    assert 'request_skill_for_intent' not in TOOLS


def test_model_visible_tools_are_registered():
    exposed_names = {
        tool['function']['name']
        for tool in OPENAI_TOOLS
        if tool.get('type') == 'function'
    }

    assert exposed_names <= set(TOOLS)


def test_security_review_tools_are_model_visible_and_registered():
    exposed_names = {
        tool['function']['name']
        for tool in OPENAI_TOOLS
        if tool.get('type') == 'function'
    }

    for name in {'discover_review_targets', 'search_owasp_reference'}:
        assert name in exposed_names
        assert name in TOOLS


def test_owasp_index_admin_tools_are_registered_but_not_model_visible():
    exposed_names = {
        tool['function']['name']
        for tool in OPENAI_TOOLS
        if tool.get('type') == 'function'
    }

    for name in {'validate_owasp_corpus', 'rebuild_owasp_reference_index'}:
        assert name not in exposed_names
        assert name in TOOLS


def test_run_shell_schema_lists_actual_allowed_commands_only():
    run_shell_schema = next(
        tool for tool in OPENAI_TOOLS
        if tool['function']['name'] == 'run_shell'
    )
    description = run_shell_schema['function']['description']

    for command in ALLOWED_COMMANDS:
        assert command in description
    assert 'sed' not in description


def test_create_skill_schema_requires_structured_inputs_and_outputs():
    create_skill_schema = next(
        tool for tool in OPENAI_TOOLS
        if tool['function']['name'] == 'create_skill'
    )
    json_payload = create_skill_schema['function']['parameters']['properties']['json_payload']

    for field in ('inputs', 'outputs'):
        value_schema = json_payload['properties'][field]['additionalProperties']
        assert value_schema['type'] == 'object'
        assert value_schema['required'] == ['type', 'description']
        assert value_schema['properties']['type']['type'] == 'string'
        assert value_schema['properties']['description']['type'] == 'string'
