from __future__ import annotations

from typing import Any

from flask import jsonify

from agent.runtime import AgentRuntime
from agent.runtime_state import notify_stream
from agent.metrics import elapsed_ms, estimate_messages_chars, now_ms
from system_prompt.system_prompt import build_system_prompt
from tools.tools import OPENAI_TOOLS


def measure_baseline(agent: Any) -> dict[str, Any]:
    system_prompt = build_system_prompt()
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': 'Reply OK.'},
    ]
    start_ms = now_ms()
    ttft_ms: float | None = None
    first_output_kind: str | None = None

    stream = agent.client.chat.completions.create(
        model=agent.model,
        messages=messages,
        tools=OPENAI_TOOLS,
        temperature=0,
        max_tokens=1,
        stream=True,
    )

    for chunk in stream:
        choice = chunk.choices[0]
        delta = choice.delta
        if ttft_ms is None and getattr(delta, 'content', None):
            ttft_ms = elapsed_ms(start_ms)
            first_output_kind = 'content'
        if ttft_ms is None and getattr(delta, 'tool_calls', None):
            ttft_ms = elapsed_ms(start_ms)
            first_output_kind = 'tool_call'

    result = {
        'status': 'ok',
        'model': agent.model,
        'baseline_total_ms': elapsed_ms(start_ms),
        'baseline_ttft_ms': ttft_ms,
        'first_output_kind': first_output_kind,
        'estimated_prompt_chars': estimate_messages_chars(messages),
        'estimated_system_prompt_chars': len(system_prompt),
    }
    agent.metrics.set_baseline(result)
    return result


def _reserve_baseline(runtime: AgentRuntime) -> bool:
    with runtime.state_lock:
        agent = runtime.agent
        if agent.generation.is_busy():
            return False
        with agent.lock:
            agent.is_generating = True
    notify_stream(agent)
    return True


def _finish_baseline(agent: Any) -> None:
    with agent.lock:
        agent.is_generating = False
    notify_stream(agent)


def register_metrics_routes(app: Any, runtime: AgentRuntime) -> None:
    @app.post('/api/metrics/baseline')
    def baseline_metrics() -> Any:
        if not _reserve_baseline(runtime):
            return jsonify({'status': 'error', 'error': 'Generation already in progress'}), 409

        agent = runtime.agent
        try:
            return jsonify(measure_baseline(agent))
        except Exception as exc:
            result = {'status': 'error', 'error': str(exc)}
            agent.metrics.set_baseline(result)
            return jsonify(result), 500
        finally:
            _finish_baseline(agent)
