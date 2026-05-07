from __future__ import annotations

from scripts import benchmark_model


def test_summarize_runs_computes_percentiles():
    summary = benchmark_model.summarize_runs(
        'vanilla',
        [
            {
                'ttft_ms': 100.0,
                'total_ms': 200.0,
                'prompt_chars': 10,
                'system_chars': 0,
                'tools_enabled': False,
            },
            {
                'ttft_ms': 300.0,
                'total_ms': 500.0,
                'prompt_chars': 10,
                'system_chars': 0,
                'tools_enabled': False,
            },
        ],
    )

    assert summary['scenario'] == 'vanilla'
    assert summary['ttft_ms']['p50'] in {100.0, 300.0}
    assert summary['total_ms']['max'] == 500.0


def test_markdown_table_contains_scenarios():
    table = benchmark_model.markdown_table({
        'scenarios': [
            {
                'scenario': 'vanilla',
                'runs': 1,
                'ttft_ms': {'p50': 10, 'p90': 10},
                'total_ms': {'p50': 20, 'p90': 20},
                'prompt_chars': 9,
                'system_chars': 0,
                'tools_enabled': False,
            }
        ]
    })

    assert '| vanilla |' in table
