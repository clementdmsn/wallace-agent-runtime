from __future__ import annotations

import logging
from typing import Any

from agent.run_trace import RunTrace
from agent.skill_selection import latest_user_text

logger = logging.getLogger(__name__)


def append_message_locked(agent: Any, submitted: dict[str, Any]) -> None:
    agent.messages.append(submitted)
    if submitted.get('role') == 'user':
        agent.tool_events = []
        agent.pending_approval = None
        agent._reset_skill_state()


def snapshot_messages(agent: Any) -> list[dict[str, Any]]:
    with agent.lock:
        return [dict(message) for message in agent.messages]


def snapshot_tool_events(agent: Any) -> list[dict[str, Any]]:
    with agent.lock:
        return [dict(event) for event in agent.tool_events]


def snapshot_runtime_metrics(agent: Any) -> dict[str, object]:
    with agent.lock:
        return agent.metrics.snapshot()


def is_busy(agent: Any) -> bool:
    with agent.lock:
        return agent.is_generating


def is_current_run(agent: Any, run_id: int) -> bool:
    return run_id == agent.run_id


def notify_stream(agent: Any) -> None:
    callback = agent.on_stream
    if callback is not None:
        try:
            callback()
        except Exception:
            logger.exception('stream notification callback failed')


def trace(agent: Any, event: str, **fields: Any) -> None:
    run_trace = agent.run_trace
    if run_trace is not None:
        run_trace.record(event, **fields)


def start_run_trace(run_id: int) -> RunTrace:
    return RunTrace.start(run_id)


def reserve_generation(agent: Any, submitted: dict[str, Any] | None = None) -> int | None:
    with agent.lock:
        if agent.is_generating:
            return None
        if submitted is not None:
            append_message_locked(agent, submitted)
        agent.is_generating = True
        agent.last_error = ''
        agent.loop_turn = 0
        agent.run_id += 1
        current_run_id = agent.run_id
        system_prompt = str(agent.messages[0].get('content', '')) if agent.messages else ''
        agent.metrics.start_request(current_run_id, agent.model, len(system_prompt))
        agent.run_trace = start_run_trace(current_run_id)
        latest_user = latest_user_text(agent)
        trace(
            agent,
            'run_started',
            model=agent.model,
            system_prompt_chars=len(system_prompt),
            user_message=agent.run_trace.payload(latest_user) if agent.run_trace else latest_user,
        )
    notify_stream(agent)
    return current_run_id


def finish_generation(agent: Any, run_id: int) -> None:
    with agent.lock:
        if not is_current_run(agent, run_id):
            return
        agent.is_generating = False
        agent.metrics.finish_request(run_id)
        last_error = agent.last_error
        metrics = agent.metrics.snapshot().get('last_request')
        trace(agent, 'run_finished', last_error=last_error, metrics=metrics)
        agent.run_trace = None
    notify_stream(agent)
