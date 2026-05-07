from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import OpenAI

from config import SETTINGS


SCENARIOS = ('vanilla', 'prompt', 'prompt-tools')


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def elapsed_ms(start_ms: float) -> float:
    return round(now_ms() - start_ms, 2)


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * pct)
    return round(ordered[index], 2)


def build_request(scenario: str, prompt: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    if scenario == 'vanilla':
        return [{'role': 'user', 'content': prompt}], None

    from system_prompt.system_prompt import build_system_prompt

    messages = [
        {'role': 'system', 'content': build_system_prompt()},
        {'role': 'user', 'content': prompt},
    ]
    if scenario == 'prompt':
        return messages, None
    if scenario == 'prompt-tools':
        from tools.tools import OPENAI_TOOLS

        return messages, OPENAI_TOOLS

    raise ValueError(f'unknown scenario: {scenario}')


def estimate_messages_chars(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        total += len(str(message.get('role', '')))
        total += len(str(message.get('content', '')))
    return total


def run_once(
    client: OpenAI,
    *,
    model: str,
    scenario: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    messages, tools = build_request(scenario, prompt)
    start_ms = now_ms()
    ttft_ms: float | None = None
    first_output_kind: str | None = None
    output_parts: list[str] = []
    tool_delta_seen = False

    kwargs: dict[str, Any] = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'stream': True,
    }
    if tools is not None:
        kwargs['tools'] = tools

    stream = client.chat.completions.create(**kwargs)

    for chunk in stream:
        choice = chunk.choices[0]
        delta = choice.delta

        text = getattr(delta, 'content', None)
        if text:
            if ttft_ms is None:
                ttft_ms = elapsed_ms(start_ms)
                first_output_kind = 'content'
            output_parts.append(text)

        delta_tool_calls = getattr(delta, 'tool_calls', None) or []
        if delta_tool_calls:
            tool_delta_seen = True
            if ttft_ms is None:
                ttft_ms = elapsed_ms(start_ms)
                first_output_kind = 'tool_call'

    output = ''.join(output_parts)
    return {
        'scenario': scenario,
        'model': model,
        'ttft_ms': ttft_ms,
        'total_ms': elapsed_ms(start_ms),
        'first_output_kind': first_output_kind,
        'prompt_chars': estimate_messages_chars(messages),
        'system_chars': len(str(messages[0].get('content', ''))) if messages and messages[0].get('role') == 'system' else 0,
        'tools_enabled': tools is not None,
        'tool_delta_seen': tool_delta_seen,
        'output_chars': len(output),
        'output': output,
    }


def summarize_runs(scenario: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    ttfts = [run['ttft_ms'] for run in runs if isinstance(run.get('ttft_ms'), (int, float))]
    totals = [run['total_ms'] for run in runs if isinstance(run.get('total_ms'), (int, float))]

    return {
        'scenario': scenario,
        'runs': len(runs),
        'ttft_ms': {
            'min': percentile(ttfts, 0.0),
            'p50': percentile(ttfts, 0.5),
            'p90': percentile(ttfts, 0.9),
            'max': percentile(ttfts, 1.0),
            'mean': round(statistics.mean(ttfts), 2) if ttfts else None,
        },
        'total_ms': {
            'min': percentile(totals, 0.0),
            'p50': percentile(totals, 0.5),
            'p90': percentile(totals, 0.9),
            'max': percentile(totals, 1.0),
            'mean': round(statistics.mean(totals), 2) if totals else None,
        },
        'prompt_chars': runs[0]['prompt_chars'] if runs else None,
        'system_chars': runs[0]['system_chars'] if runs else None,
        'tools_enabled': runs[0]['tools_enabled'] if runs else None,
    }


def markdown_table(summary: dict[str, Any]) -> str:
    rows = [
        '| Scenario | Runs | TTFT p50 | TTFT p90 | Total p50 | Total p90 | Prompt chars | System chars | Tools |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |',
    ]
    for item in summary['scenarios']:
        rows.append(
            '| {scenario} | {runs} | {ttft_p50}ms | {ttft_p90}ms | {total_p50}ms | {total_p90}ms | {prompt_chars} | {system_chars} | {tools} |'.format(
                scenario=item['scenario'],
                runs=item['runs'],
                ttft_p50=item['ttft_ms']['p50'],
                ttft_p90=item['ttft_ms']['p90'],
                total_p50=item['total_ms']['p50'],
                total_p90=item['total_ms']['p90'],
                prompt_chars=item['prompt_chars'],
                system_chars=item['system_chars'],
                tools='yes' if item['tools_enabled'] else 'no',
            )
        )
    return '\n'.join(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Benchmark raw model latency against Wallace prompt/tool scenarios.')
    parser.add_argument('--base-url', default=SETTINGS.base_url)
    parser.add_argument('--api-key', default=SETTINGS.api_key)
    parser.add_argument('--model', default=SETTINGS.model_name)
    parser.add_argument('--scenario', choices=(*SCENARIOS, 'all'), default='all')
    parser.add_argument('--prompt', default='Reply OK.')
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--max-tokens', type=int, default=16)
    parser.add_argument('--temperature', type=float, default=0.0)
    parser.add_argument('--json', action='store_true', help='Print JSON instead of a markdown table.')
    parser.add_argument('--include-output', action='store_true', help='Include per-run model output in JSON.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenarios = list(SCENARIOS) if args.scenario == 'all' else [args.scenario]
    client = OpenAI(base_url=args.base_url, api_key=args.api_key)
    all_runs: dict[str, list[dict[str, Any]]] = {}

    for scenario in scenarios:
        scenario_runs = []
        for index in range(args.runs):
            run = run_once(
                client,
                model=args.model,
                scenario=scenario,
                prompt=args.prompt,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
            scenario_runs.append(run)
            print(
                f'{scenario} run {index + 1}/{args.runs}: TTFT={run["ttft_ms"]}ms total={run["total_ms"]}ms',
                file=sys.stderr,
            )
        all_runs[scenario] = scenario_runs

    summary = {
        'model': args.model,
        'base_url': args.base_url,
        'prompt': args.prompt,
        'runs_per_scenario': args.runs,
        'scenarios': [
            summarize_runs(scenario, all_runs[scenario])
            for scenario in scenarios
        ],
    }

    if args.json:
        payload = dict(summary)
        if args.include_output:
            payload['raw_runs'] = all_runs
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(markdown_table(summary))

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
