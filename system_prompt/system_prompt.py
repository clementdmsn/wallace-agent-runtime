
from pathlib import Path
from typing import Any


# CONSTITUTION = [
#     "codex_core_identity.md",
#     "codex_core_tools.md",
#     "codex_core_execution.md",
#     "codex_core_style.md",
#     "codex_mode_code_understanding.md",
#     "codex_mode_file_editing.md",
#     "codex_mode_skill_authoring.md",
#     "codex_mode_skill_routing.md",
# ]

CONSTITUTION = [
        "system_prompt.md"
        ]

PROMPT_DIR = Path(__file__).resolve().parent


def build_system_prompt() -> str:
    fragments = []
    for file in CONSTITUTION:
        fragments.append((PROMPT_DIR / file).read_text(encoding='utf-8').strip())

    return '\n\n'.join(fragments)


def build_skill_prompt_section(selected_skill: dict[str, Any] | None) -> str:
    if not selected_skill or not selected_skill.get('skill_name'):
        return ''

    parts = [
        '# TASK-SPECIFIC PROCEDURE',
        (
            'A relevant skill procedure was selected for the current user request. '
            'Follow this procedure as binding workflow guidance. If part of it is '
            'impossible or inapplicable, say why and continue with the closest valid fallback.'
        ),
        f"Selected skill: {selected_skill['skill_name']}",
    ]

    overrides = selected_skill.get('procedure_overrides') or []
    if overrides:
        parts.append('Procedure overrides:')
        parts.extend(f'- {item}' for item in overrides)

    recommended = selected_skill.get('recommended_tool_calls') or []
    if recommended:
        parts.append('Recommended tool calls:')
        for call in recommended:
            tool = call.get('tool')
            arguments = call.get('arguments') or {}
            reason = call.get('reason')
            line = f'- {tool}({arguments})'
            if reason:
                line += f': {reason}'
            parts.append(line)

    allowed = selected_skill.get('allowed_tools') or []
    if allowed:
        parts.append(f"Allowed tools for this procedure: {', '.join(allowed)}")

    forbidden = selected_skill.get('forbidden_tool_calls') or []
    if forbidden:
        parts.append('Forbidden tool calls:')
        for call in forbidden:
            tool = call.get('tool')
            reason = call.get('reason', 'Forbidden by the selected procedure.')
            parts.append(f'- {tool}: {reason}')

    procedure = str(selected_skill.get('procedure') or '').strip()
    if procedure:
        parts.extend(['Procedure:', procedure])

    return '\n'.join(parts)


def build_request_system_prompt(
    base_prompt: str,
    selected_skill: dict[str, Any] | None = None,
) -> str:
    skill_section = build_skill_prompt_section(selected_skill)
    if not skill_section:
        return base_prompt
    return f'{base_prompt.strip()}\n\n{skill_section}'
