from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


MIN_SOURCE_CHARS = 800
MIN_SOURCE_LINES = 10
MIN_ALIAS_LINES = 8
MIN_ALIAS_CHARS = 800
MIN_NET_SAVINGS_CHARS = 400
MAX_REFS_PER_CALL = 20
MAX_REFS_PER_MESSAGE = 5


@dataclass(frozen=True)
class LineCandidate:
    source_message: int
    source_start: int
    target_message: int
    target_start: int
    line_count: int
    char_count: int
    digest: str

    @property
    def source_end(self) -> int:
        return self.source_start + self.line_count

    @property
    def target_end(self) -> int:
        return self.target_start + self.line_count


def _split_lines(content: str) -> list[str]:
    return content.replace('\r\n', '\n').replace('\r', '\n').split('\n')


def _range_text(lines: list[str], start: int, end: int) -> str:
    return '\n'.join(lines[start:end])


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


def _eligible_tool_message(message: dict[str, Any]) -> bool:
    content = message.get('content')
    if message.get('role') != 'tool' or not isinstance(content, str):
        return False
    if len(content) < MIN_SOURCE_CHARS:
        return False
    return len(_split_lines(content)) >= MIN_SOURCE_LINES


def _build_alias(candidate: LineCandidate) -> str:
    return (
        f'[CTXREF msg={candidate.source_message} '
        f'lines={candidate.source_start + 1}-{candidate.source_end} '
        f'hash={candidate.digest} exact]'
    )


def _number_source_content(content: str, message_index: int, role: str) -> str:
    lines = _split_lines(content)
    numbered = '\n'.join(f'L{index}: {line}' for index, line in enumerate(lines, start=1))
    return f'[CTXBLOCK msg={message_index} role={role}]\n{numbered}\n[/CTXBLOCK]'


def _line_window_key(lines: list[str], start: int) -> tuple[str, tuple[str, ...]]:
    window = tuple(lines[start:start + MIN_ALIAS_LINES])
    text = '\n'.join(window)
    return _digest(text), window


def _find_candidates(messages: list[dict[str, Any]]) -> list[LineCandidate]:
    previous_windows: dict[tuple[str, tuple[str, ...]], list[tuple[int, int]]] = {}
    message_lines: dict[int, list[str]] = {}
    candidates: list[LineCandidate] = []

    for message_index, message in enumerate(messages):
        if not _eligible_tool_message(message):
            continue

        lines = _split_lines(str(message.get('content', '')))
        message_lines[message_index] = lines
        if len(lines) < MIN_ALIAS_LINES:
            continue

        for target_start in range(0, len(lines) - MIN_ALIAS_LINES + 1):
            key = _line_window_key(lines, target_start)
            for source_message, source_start in previous_windows.get(key, []):
                source_lines = message_lines[source_message]
                line_count = MIN_ALIAS_LINES
                while (
                    source_start + line_count < len(source_lines)
                    and target_start + line_count < len(lines)
                    and source_lines[source_start + line_count] == lines[target_start + line_count]
                ):
                    line_count += 1

                text = _range_text(lines, target_start, target_start + line_count)
                char_count = len(text)
                if line_count < MIN_ALIAS_LINES:
                    continue
                if char_count < MIN_ALIAS_CHARS and line_count < MIN_ALIAS_LINES:
                    continue
                candidates.append(
                    LineCandidate(
                        source_message=source_message,
                        source_start=source_start,
                        target_message=message_index,
                        target_start=target_start,
                        line_count=line_count,
                        char_count=char_count,
                        digest=_digest(_range_text(source_lines, source_start, source_start + line_count)),
                    )
                )

        for source_start in range(0, len(lines) - MIN_ALIAS_LINES + 1):
            previous_windows.setdefault(_line_window_key(lines, source_start), []).append((message_index, source_start))

    return candidates


def _select_candidates(candidates: list[LineCandidate]) -> list[LineCandidate]:
    selected: list[LineCandidate] = []
    occupied_by_message: dict[int, set[int]] = {}
    refs_by_message: dict[int, int] = {}
    compacted_targets: set[int] = set()
    source_messages: set[int] = set()

    for candidate in sorted(candidates, key=lambda item: (item.char_count, item.line_count), reverse=True):
        if len(selected) >= MAX_REFS_PER_CALL:
            break
        if candidate.source_message in compacted_targets:
            continue
        if candidate.target_message in source_messages:
            continue
        if refs_by_message.get(candidate.target_message, 0) >= MAX_REFS_PER_MESSAGE:
            continue
        occupied = occupied_by_message.setdefault(candidate.target_message, set())
        target_range = set(range(candidate.target_start, candidate.target_end))
        if occupied & target_range:
            continue
        occupied.update(target_range)
        source_messages.add(candidate.source_message)
        compacted_targets.add(candidate.target_message)
        refs_by_message[candidate.target_message] = refs_by_message.get(candidate.target_message, 0) + 1
        selected.append(candidate)

    return sorted(selected, key=lambda item: (item.target_message, item.target_start))


def _replace_target_ranges(content: str, candidates: list[LineCandidate]) -> str:
    lines = _split_lines(content)
    output: list[str] = []
    cursor = 0
    for candidate in sorted(candidates, key=lambda item: item.target_start):
        output.extend(lines[cursor:candidate.target_start])
        output.append(_build_alias(candidate))
        cursor = candidate.target_end
    output.extend(lines[cursor:])
    return '\n'.join(output)


def _empty_stats(original_chars: int) -> dict[str, Any]:
    return {
        'context_reference_count': 0,
        'context_reference_saved_chars': 0,
        'context_reference_source_count': 0,
        'uncompacted_content_chars': original_chars,
        'compacted_content_chars': original_chars,
        'context_reference_aliases': [],
        'context_reference_transforms': [],
    }


def _alias_metadata(candidate: LineCandidate) -> dict[str, Any]:
    return {
        'alias': _build_alias(candidate),
        'source_message': candidate.source_message,
        'target_message': candidate.target_message,
        'source_lines': f'{candidate.source_start + 1}-{candidate.source_end}',
        'target_lines': f'{candidate.target_start + 1}-{candidate.target_end}',
        'line_count': candidate.line_count,
        'char_count': candidate.char_count,
        'hash': candidate.digest,
    }


def compact_context_references(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    original_chars = sum(len(str(message.get('content', ''))) for message in messages)
    candidates = _select_candidates(_find_candidates(messages))
    if not candidates:
        return [dict(message) for message in messages], _empty_stats(original_chars)

    by_target: dict[int, list[LineCandidate]] = {}
    source_messages = {candidate.source_message for candidate in candidates}
    for candidate in candidates:
        by_target.setdefault(candidate.target_message, []).append(candidate)

    compacted = [dict(message) for message in messages]
    for message_index in sorted(source_messages):
        content = compacted[message_index].get('content')
        if isinstance(content, str):
            compacted[message_index]['content'] = _number_source_content(
                content,
                message_index,
                str(compacted[message_index].get('role', '')),
            )

    for message_index, target_candidates in by_target.items():
        content = compacted[message_index].get('content')
        if isinstance(content, str):
            compacted[message_index]['content'] = _replace_target_ranges(content, target_candidates)

    compacted_chars = sum(len(str(message.get('content', ''))) for message in compacted)
    saved_chars = original_chars - compacted_chars
    if saved_chars < MIN_NET_SAVINGS_CHARS:
        return [dict(message) for message in messages], _empty_stats(original_chars)

    transforms = []
    for message_index in sorted(source_messages):
        content = str(compacted[message_index].get('content', ''))
        transforms.append({
            'message': message_index,
            'role': compacted[message_index].get('role'),
            'kind': 'source_numbered',
            'has_ctxblock': content.startswith('[CTXBLOCK '),
            'before_chars': len(str(messages[message_index].get('content', ''))),
            'after_chars': len(content),
        })
    for message_index, target_candidates in sorted(by_target.items()):
        content = str(compacted[message_index].get('content', ''))
        transforms.append({
            'message': message_index,
            'role': compacted[message_index].get('role'),
            'kind': 'target_aliased',
            'has_ctxref': '[CTXREF ' in content,
            'before_chars': len(str(messages[message_index].get('content', ''))),
            'after_chars': len(content),
            'aliases': [_build_alias(candidate) for candidate in target_candidates],
        })

    return compacted, {
        'context_reference_count': len(candidates),
        'context_reference_saved_chars': saved_chars,
        'context_reference_source_count': len(source_messages),
        'uncompacted_content_chars': original_chars,
        'compacted_content_chars': compacted_chars,
        'context_reference_aliases': [_alias_metadata(candidate) for candidate in candidates],
        'context_reference_transforms': transforms,
    }
