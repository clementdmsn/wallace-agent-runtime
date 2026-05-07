from __future__ import annotations

from agent.context_compaction import compact_context_references


def long_lines(prefix: str, count: int = 14) -> str:
    return '\n'.join(
        f'{prefix} line {index:02d} with enough repeated detail to pass conservative compaction thresholds.'
        for index in range(1, count + 1)
    )


def test_context_compaction_noops_without_duplicates():
    messages = [
        {'role': 'system', 'content': 'base'},
        {'role': 'tool', 'tool_call_id': 'call-1', 'content': long_lines('alpha')},
        {'role': 'tool', 'tool_call_id': 'call-2', 'content': long_lines('beta')},
    ]

    compacted, stats = compact_context_references(messages)

    assert compacted == messages
    assert stats['context_reference_count'] == 0
    assert stats['context_reference_saved_chars'] == 0


def test_context_compaction_replaces_later_duplicate_tool_output():
    repeated = long_lines('same')
    messages = [
        {'role': 'system', 'content': 'base'},
        {'role': 'tool', 'tool_call_id': 'call-1', 'content': repeated},
        {'role': 'tool', 'tool_call_id': 'call-2', 'content': repeated},
    ]

    compacted, stats = compact_context_references(messages)

    assert compacted[1]['content'].startswith('[CTXBLOCK msg=1 role=tool]\nL1: same line 01')
    assert compacted[1]['content'].endswith('\n[/CTXBLOCK]')
    assert compacted[2]['content'].startswith('[CTXREF msg=1 lines=1-14 hash=')
    assert ' exact]' in compacted[2]['content']
    assert stats['context_reference_count'] == 1
    assert stats['context_reference_source_count'] == 1
    assert stats['context_reference_saved_chars'] > 400
    assert stats['context_reference_aliases'][0]['alias'].startswith('[CTXREF msg=1 lines=1-14 hash=')
    assert stats['context_reference_aliases'][0]['source_lines'] == '1-14'
    assert stats['context_reference_transforms'] == [
        {
            'message': 1,
            'role': 'tool',
            'kind': 'source_numbered',
            'has_ctxblock': True,
            'before_chars': len(repeated),
            'after_chars': len(compacted[1]['content']),
        },
        {
            'message': 2,
            'role': 'tool',
            'kind': 'target_aliased',
            'has_ctxref': True,
            'before_chars': len(repeated),
            'after_chars': len(compacted[2]['content']),
            'aliases': [stats['context_reference_aliases'][0]['alias']],
        },
    ]
    assert messages[1]['content'] == repeated
    assert messages[2]['content'] == repeated


def test_context_compaction_replaces_repeated_range_inside_later_tool_message():
    repeated = long_lines('block')
    messages = [
        {'role': 'system', 'content': 'base'},
        {'role': 'tool', 'tool_call_id': 'call-1', 'content': repeated},
        {'role': 'tool', 'tool_call_id': 'call-2', 'content': f'before\n{repeated}\nafter'},
    ]

    compacted, stats = compact_context_references(messages)

    assert compacted[2]['content'].startswith('before\n[CTXREF msg=1 lines=1-14 hash=')
    assert compacted[2]['content'].endswith(' exact]\nafter')
    assert stats['context_reference_count'] == 1


def test_context_compaction_ignores_system_and_user_duplicates():
    repeated = long_lines('same')
    messages = [
        {'role': 'system', 'content': repeated},
        {'role': 'user', 'content': repeated},
        {'role': 'assistant', 'content': repeated},
    ]

    compacted, stats = compact_context_references(messages)

    assert compacted == messages
    assert stats['context_reference_count'] == 0


def test_context_compaction_selects_largest_overlapping_range():
    repeated = long_lines('overlap', 18)
    messages = [
        {'role': 'system', 'content': 'base'},
        {'role': 'tool', 'tool_call_id': 'call-1', 'content': repeated},
        {'role': 'tool', 'tool_call_id': 'call-2', 'content': repeated},
    ]

    compacted, stats = compact_context_references(messages)

    assert compacted[2]['content'].count('[CTXREF') == 1
    assert 'lines=1-18' in compacted[2]['content']
    assert stats['context_reference_count'] == 1


def test_context_compaction_does_not_compact_a_message_used_as_source():
    repeated = long_lines('chain', 18)
    messages = [
        {'role': 'system', 'content': 'base'},
        {'role': 'tool', 'tool_call_id': 'call-1', 'content': repeated},
        {'role': 'tool', 'tool_call_id': 'call-2', 'content': repeated},
        {'role': 'tool', 'tool_call_id': 'call-3', 'content': repeated},
    ]

    compacted, stats = compact_context_references(messages)

    assert compacted[1]['content'].startswith('[CTXBLOCK msg=1 role=tool]')
    assert compacted[2]['content'].startswith('[CTXREF msg=1 lines=1-18 hash=')
    assert compacted[3]['content'].startswith('[CTXREF msg=1 lines=1-18 hash=')
    assert '[CTXBLOCK msg=2' not in compacted[2]['content']
    assert stats['context_reference_count'] == 2
