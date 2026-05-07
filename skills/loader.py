from __future__ import annotations

import json
import logging
from pathlib import Path

from config import SETTINGS
from sandbox import configured_project_path, project_relative_path
from skills.intent import ACTION_KEYWORDS, normalize_text
from skills.skills_registry import Skill

logger = logging.getLogger(__name__)


SKILL_METADATA_DIR = getattr(SETTINGS, 'skill_metadata_dir', 'skill_catalog/metadatas')
SKILL_PROCEDURE_DIR = getattr(SETTINGS, 'skill_procedure_dir', 'skill_catalog/procedures')


# Loader turns project-owned skill metadata/procedure files into Skill objects.
# It does not select skills; it only builds the in-memory registry.
def read_optional_text(path: Path) -> str:
    try:
        if path.exists() and path.is_file():
            return path.read_text(encoding='utf-8')
    except Exception as exc:
        logger.warning('failed to read skill procedure %s: %s', path, exc)
        return ''
    return ''


def candidate_procedure_paths(stem: str) -> list[Path]:
    return [
        configured_project_path(str(Path(SKILL_PROCEDURE_DIR) / f'{stem}.md')),
        configured_project_path(str(Path(SKILL_METADATA_DIR) / f'{stem}.md')),
        configured_project_path(f'skill_catalog/{stem}.md'),
    ]


def load_skill_procedure(stem: str) -> tuple[str, str]:
    for candidate in candidate_procedure_paths(stem):
        text = read_optional_text(candidate)
        if text:
            try:
                relative = project_relative_path(candidate)
            except Exception:
                relative = str(candidate)
            return text, relative
    return '', ''


def load_skill_from_metadata(metadata_path: Path) -> Skill | None:
    try:
        raw = metadata_path.read_text(encoding='utf-8')
        data = json.loads(raw)
    except Exception as exc:
        logger.warning('failed to load skill metadata %s: %s', metadata_path, exc)
        return None

    if not isinstance(data, dict):
        logger.warning('skill metadata %s is not a JSON object', metadata_path)
        return None

    name = str(data.get('name') or metadata_path.stem).strip()
    if not name:
        logger.warning('skill metadata %s has an empty name', metadata_path)
        return None

    inputs = data.get('inputs')
    if not isinstance(inputs, dict):
        inputs = {}

    parameter_schema = {
        'type': 'object',
        'properties': inputs,
        'required': sorted(inputs.keys()),
        'additionalProperties': False,
    }

    procedure, procedure_path = load_skill_procedure(metadata_path.stem)

    categories = tuple(str(item) for item in data.get('categories', []) if isinstance(item, str))
    when_to_use = tuple(str(item) for item in data.get('when_to_use', []) if isinstance(item, str))
    when_not_to_use = tuple(str(item) for item in data.get('when_not_to_use', []) if isinstance(item, str))
    trigger_actions = tuple(str(item) for item in data.get('trigger_actions', []) if isinstance(item, str))
    exclusions = tuple(str(item) for item in data.get('exclusions', []) if isinstance(item, str))
    examples = tuple(str(item) for item in data.get('examples', []) if isinstance(item, str))
    preconditions = tuple(str(item) for item in data.get('preconditions', []) if isinstance(item, str))
    tools_required = tuple(str(item) for item in data.get('tools_required', []) if isinstance(item, str))

    tags = frozenset(
        normalize_text(' '.join(
            [name, str(data.get('summary', '')), str(data.get('description', ''))]
            + list(categories)
            + list(trigger_actions)
            + list(examples)
        )).split()
    )

    supported_actions: set[str] = set()
    action_text = normalize_text(' '.join(trigger_actions + when_to_use + examples))
    action_tokens = set(action_text.split())
    for action, keywords in ACTION_KEYWORDS.items():
        if action_tokens & keywords:
            supported_actions.add(action)

    required_args = frozenset(
        key for key, value in inputs.items()
        if isinstance(key, str) and isinstance(value, dict)
    )

    filetypes: set[str] = set()
    text_for_filetypes = ' '.join(trigger_actions + when_to_use + examples + when_not_to_use).lower()
    mapping = {
        'python': 'py',
        'javascript': 'js',
        'typescript': 'ts',
        'tsx': 'tsx',
        'jsx': 'jsx',
        '.py': 'py',
        '.js': 'js',
        '.ts': 'ts',
        '.tsx': 'tsx',
        '.jsx': 'jsx',
    }
    for marker, filetype in mapping.items():
        if marker in text_for_filetypes:
            filetypes.add(filetype)

    domains = set(categories)
    if any(cat.startswith('code') or cat.endswith('code') for cat in categories) or 'function' in tags:
        domains.add('code')
    if 'skill' in tags:
        domains.add('skills')

    default_score = data.get('default_score', 0.5)
    try:
        default_score = float(default_score)
    except Exception:
        logger.warning('skill metadata %s has invalid default_score: %r', metadata_path, default_score)
        default_score = 0.5

    metadata_rel = project_relative_path(metadata_path)

    return Skill(
        name=name,
        description=str(data.get('description') or data.get('summary') or name),
        implementation_name=name,
        parameters=parameter_schema,
        procedure=procedure,
        metadata_path=metadata_rel,
        procedure_path=procedure_path,
        when_to_use=when_to_use,
        when_not_to_use=when_not_to_use,
        examples=examples,
        category=categories[0] if categories else 'general',
        tags=tags,
        supported_actions=frozenset(supported_actions),
        supported_domains=frozenset(domains),
        supported_filetypes=frozenset(filetypes),
        required_args=required_args,
        tools_required=tools_required,
        exclusions=exclusions,
        preconditions=preconditions,
        priority=max(0, min(100, int(default_score * 100))),
        specificity=max(0, min(100, 20 + 5 * len(tools_required) + 3 * len(when_not_to_use))),
        default_score=default_score,
    )


def load_skills() -> list[Skill]:
    metadata_root = configured_project_path(SKILL_METADATA_DIR)
    metadata_root.mkdir(parents=True, exist_ok=True)
    skills: list[Skill] = []

    for metadata_path in sorted(metadata_root.glob('*.json')):
        skill = load_skill_from_metadata(metadata_path)
        if skill is not None:
            skills.append(skill)

    return skills
