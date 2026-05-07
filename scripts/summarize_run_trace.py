from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def latest(events: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get('event') == name:
            return event
    return None


def summarize(path: Path) -> str:
    events = load_events(path)
    started = latest(events, 'run_started') or {}
    finished = latest(events, 'run_finished')
    skill = latest(events, 'skill_selection_finished') or {}
    model_failed = latest(events, 'model_call_failed')
    assistant = latest(events, 'model_call_finished')
    tool_events = [event for event in events if event.get('event') == 'tool_call_finished']

    lines = [
        f'Trace: {path}',
        f'Trace ID: {(events[0] or {}).get("trace_id", "unknown") if events else "unknown"}',
        f'Status: {"complete" if finished else "incomplete"}',
        f'User: {started.get("user_message", "")}',
        f'Skill: {skill.get("skill_name") or "none"}',
    ]

    if model_failed:
        lines.append(f'Model error: {model_failed.get("error", "")}')
    elif assistant:
        message = assistant.get('assistant_message') or {}
        content = str(message.get('content') or '').strip()
        if content:
            lines.append(f'Assistant: {content}')
        calls = message.get('tool_calls') or []
        if calls:
            lines.append(f'Model tool calls: {len(calls)}')

    if tool_events:
        lines.append('Tools:')
        for event in tool_events:
            lines.append(
                f'- {event.get("tool")} status={event.get("status")} '
                f'duration_ms={event.get("duration_ms")}'
            )

    metrics = (finished or {}).get('metrics') if finished else None
    if isinstance(metrics, dict):
        total = metrics.get('request_total_ms')
        model_calls = metrics.get('model_calls') or []
        ttfts = [call.get('ttft_ms') for call in model_calls if call.get('ttft_ms') is not None]
        lines.append(f'Request total ms: {total}')
        if ttfts:
            lines.append(f'First token ms: {ttfts[0]}')

    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description='Summarize a Wallace JSONL run trace.')
    parser.add_argument('trace_path', type=Path)
    args = parser.parse_args()
    print(summarize(args.trace_path))


if __name__ == '__main__':
    main()
