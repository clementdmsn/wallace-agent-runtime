from __future__ import annotations

from typing import Any

from skills.guidance import build_execution_guidance, merge_and_sanitize_intent_args
from skills.loader import load_skills
from skills.selection import (
    choose_skill_for_intent as _choose_skill_for_intent,
    retrieve_skill_candidates as _retrieve_skill_candidates,
)
from skills.skills_registry import Skill
from skills.stats import record_skill_event as record_skill_event


# Compatibility facade for the core skill subsystem. Other modules can keep
# importing from skills.skills while implementation details live in focused files.
SKILLS: list[Skill] = load_skills()
SKILLS_BY_NAME: dict[str, Skill] = {skill.name: skill for skill in SKILLS}


def refresh_skill_registry() -> None:
    global SKILLS, SKILLS_BY_NAME

    SKILLS = load_skills()
    SKILLS_BY_NAME = {skill.name: skill for skill in SKILLS}


def retrieve_skill_candidates(
    user_text: str,
    arguments: dict[str, Any],
    k: int = 8,
) -> list[tuple[Skill, dict[str, Any]]]:
    return _retrieve_skill_candidates(SKILLS_BY_NAME, user_text, arguments, k=k)


def choose_skill_for_intent(
    user_text: str,
    arguments: dict[str, Any],
    *,
    k: int = 8,
    threshold: float = 8.0,
) -> dict[str, Any]:
    return _choose_skill_for_intent(
        SKILLS_BY_NAME,
        user_text,
        arguments,
        k=k,
        threshold=threshold,
    )


def request_skill_for_intent(
    intent: str,
    arguments: dict[str, Any] | None = None,
    k: int = 8,
    threshold: float = 8.0,
) -> dict[str, Any]:
    if not isinstance(intent, str):
        return {'status': 'error', 'error': 'intent must be a string'}
    intent = intent.strip()
    if not intent:
        return {'status': 'error', 'error': 'empty intent'}
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return {'status': 'error', 'error': 'arguments must be an object'}

    merged_args = merge_and_sanitize_intent_args(intent, arguments)
    choice = choose_skill_for_intent(intent, merged_args, k=k, threshold=threshold)
    if choice.get('status') != 'ok':
        return choice

    selected_skill_name = choice.get('skill_name')
    if not selected_skill_name:
        return {
            'status': 'ok',
            'skill_name': None,
            'arguments': merged_args,
            'selection': choice,
            'message': choice.get(
                'message',
                'No relevant skill is available. Improvise a short procedure with normal tool discipline.',
            ),
        }

    skill = get_skill(str(selected_skill_name))
    if skill is None:
        return {'status': 'error', 'error': f'selected skill is not loaded: {selected_skill_name}'}

    guidance = build_execution_guidance(skill, intent, merged_args)

    return {
        'status': 'ok',
        'skill_name': skill.name,
        'description': skill.description,
        'procedure': skill.procedure,
        'metadata_path': skill.metadata_path,
        'procedure_path': skill.procedure_path,
        'tools_required': list(skill.tools_required),
        'preconditions': list(skill.preconditions),
        'when_to_use': list(skill.when_to_use),
        'when_not_to_use': list(skill.when_not_to_use),
        'exclusions': list(skill.exclusions),
        'arguments': merged_args,
        'resolved_task_type': guidance['resolved_task_type'],
        'recommended_tool_calls': guidance['recommended_tool_calls'],
        'allowed_tools': guidance['allowed_tools'],
        'forbidden_tool_calls': guidance['forbidden_tool_calls'],
        'procedure_overrides': guidance['procedure_overrides'],
        'selection': choice,
        'message': (
            'Follow procedure_overrides first when present. Then follow the returned skill procedure. '
            'Use only registered tools for deterministic actions. If recommended_tool_calls is non-empty, '
            'make the first recommended tool call before answering.'
        ),
    }


def get_skill(skill_name: str) -> Skill | None:
    return SKILLS_BY_NAME.get(skill_name)
