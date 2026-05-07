from __future__ import annotations

from typing import Any

from flask import jsonify

from agent.agent_metrics import elapsed_ms, estimate_messages_chars, now_ms
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


def _runtime_agent(runtime_or_agent: Any) -> Any:
    return getattr(runtime_or_agent, 'agent', runtime_or_agent)


def _reserve_baseline(runtime_or_agent: Any) -> tuple[Any, bool]:
    agent = _runtime_agent(runtime_or_agent)
    state_lock = getattr(runtime_or_agent, 'state_lock', agent.lock)
    with state_lock:
        if agent.is_busy():
            return agent, False
        with agent.lock:
            agent.is_generating = True
    notify = getattr(agent, '_notify_stream', None)
    if callable(notify):
        notify()
    return agent, True


def _finish_baseline(agent: Any) -> None:
    with agent.lock:
        agent.is_generating = False
    notify = getattr(agent, '_notify_stream', None)
    if callable(notify):
        notify()


def register_metrics_routes(app: Any, runtime_or_agent: Any) -> None:
    @app.post('/api/metrics/baseline')
    def baseline_metrics() -> Any:
        agent, reserved = _reserve_baseline(runtime_or_agent)
        if not reserved:
            return jsonify({'status': 'error', 'error': 'Generation already in progress'}), 409

        try:
            return jsonify(measure_baseline(agent))
        except Exception as exc:
            result = {'status': 'error', 'error': str(exc)}
            agent.metrics.set_baseline(result)
            return jsonify(result), 500
        finally:
            _finish_baseline(agent)
