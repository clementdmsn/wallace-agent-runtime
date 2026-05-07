from __future__ import annotations

from typing import Any


def fallback_tool_call_id(run_id: int, model_call_index: int | None, tool_call_index: int) -> str:
    return f'tool_call:{run_id}:{model_call_index or 0}:{tool_call_index}'


def apply_content_delta(
    agent: Any,
    run_id: int,
    model_call_index: int | None,
    assistant_message: dict[str, Any],
    text: str,
) -> bool:
    with agent.lock:
        agent.metrics.mark_first_output(run_id, model_call_index, 'content')
        if not agent._is_current_run(run_id):
            return False
        assistant_message['content'] += text

    agent._notify_stream()
    return True


def apply_tool_call_delta(
    agent: Any,
    run_id: int,
    model_call_index: int | None,
    assistant_message: dict[str, Any],
    tool_calls_by_index: dict[int, dict[str, Any]],
    delta_tool_calls: list[Any],
) -> bool:
    with agent.lock:
        if not agent._is_current_run(run_id):
            return False
        agent.metrics.mark_first_output(run_id, model_call_index, 'tool_call')

        for delta_tool_call in delta_tool_calls:
            index = int(getattr(delta_tool_call, 'index', 0) or 0)
            current = tool_calls_by_index.setdefault(
                index,
                {
                    'id': fallback_tool_call_id(run_id, model_call_index, index),
                    'type': 'function',
                    'function': {'name': '', 'arguments': ''},
                },
            )

            tc_id = getattr(delta_tool_call, 'id', None)
            if tc_id:
                current['id'] = tc_id

            tc_type = getattr(delta_tool_call, 'type', None)
            if tc_type:
                current['type'] = tc_type

            function = getattr(delta_tool_call, 'function', None)
            if function is not None:
                fn_name = getattr(function, 'name', None)
                if fn_name:
                    current['function']['name'] = fn_name

                fn_args = getattr(function, 'arguments', None)
                if fn_args:
                    current['function']['arguments'] += fn_args

        assistant_message['tool_calls'] = [
            tool_calls_by_index[i]
            for i in sorted(tool_calls_by_index)
        ]

    agent._notify_stream()
    return True


def consume_model_stream(
    agent: Any,
    stream: Any,
    run_id: int,
    model_call_index: int | None,
    assistant_message: dict[str, Any],
) -> bool:
    tool_calls_by_index: dict[int, dict[str, Any]] = {}

    for chunk in stream:
        choice = chunk.choices[0]
        delta = choice.delta

        text = getattr(delta, 'content', None)
        if text and not apply_content_delta(
            agent,
            run_id,
            model_call_index,
            assistant_message,
            text,
        ):
            return False

        delta_tool_calls = getattr(delta, 'tool_calls', None) or []
        if delta_tool_calls and not apply_tool_call_delta(
            agent,
            run_id,
            model_call_index,
            assistant_message,
            tool_calls_by_index,
            delta_tool_calls,
        ):
            return False

    return True
