from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import SETTINGS
from sandbox import configured_sandbox_path


SKILL_INDEX_DIR = getattr(SETTINGS, 'skill_index_dir', 'skills/indexes')
SKILL_STATS_FILENAME = getattr(SETTINGS, 'skill_stats_filename', 'skills.stats.json')


# Skill stats are lightweight runtime feedback used to bias future selection.
# They live under the sandbox-owned skill index directory.
def skill_stats_path() -> Path:
    index_dir = configured_sandbox_path(SKILL_INDEX_DIR)
    index_dir.mkdir(parents=True, exist_ok=True)
    return index_dir / SKILL_STATS_FILENAME


def load_skill_stats() -> dict[str, Any]:
    stats_path = skill_stats_path()
    if not stats_path.exists():
        return {'version': 1, 'skills': {}}

    try:
        return json.loads(stats_path.read_text(encoding='utf-8'))
    except Exception:
        return {'version': 1, 'skills': {}}


def save_skill_stats(stats: dict[str, Any]) -> None:
    stats_path = skill_stats_path()
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')


def record_skill_event(skill_name: str, event: str) -> None:
    counters = {
        'retrieved': 'retrieved_count',
        'selected': 'selected_count',
        'used': 'used_count',
        'success': 'success_count',
        'failure': 'failure_count',
        'fulfilled': 'fulfilled_count',
        'rejected': 'rejected_count',
    }
    key = counters.get(event)
    if key is None:
        return

    stats = load_skill_stats()
    skill_stats = stats.setdefault('skills', {}).setdefault(skill_name, {})
    skill_stats[key] = int(skill_stats.get(key, 0)) + 1
    save_skill_stats(stats)


def record_skill_feedback(skill_name: str, task_fulfilled: bool) -> None:
    record_skill_event(skill_name, 'fulfilled' if task_fulfilled else 'rejected')


def get_skill_stats(skill_name: str) -> dict[str, int]:
    stats = load_skill_stats()
    raw = stats.get('skills', {}).get(skill_name, {})
    return {
        'retrieved_count': int(raw.get('retrieved_count', 0)),
        'selected_count': int(raw.get('selected_count', 0)),
        'used_count': int(raw.get('used_count', 0)),
        'success_count': int(raw.get('success_count', 0)),
        'failure_count': int(raw.get('failure_count', 0)),
        'fulfilled_count': int(raw.get('fulfilled_count', 0)),
        'rejected_count': int(raw.get('rejected_count', 0)),
    }


def get_skill_score_bonus(skill_name: str) -> float:
    stats = get_skill_stats(skill_name)
    success_count = stats['success_count']
    failure_count = stats['failure_count']
    fulfilled_count = stats['fulfilled_count']
    rejected_count = stats['rejected_count']
    selected_count = stats['selected_count']

    bonus = 0.0
    bonus += min(3.0, 0.2 * success_count)
    bonus -= min(3.0, 0.25 * failure_count)
    bonus += min(6.0, 0.75 * fulfilled_count)
    bonus -= min(6.0, 0.75 * rejected_count)

    if selected_count >= 3 and success_count == 0:
        bonus -= 1.0

    return bonus
