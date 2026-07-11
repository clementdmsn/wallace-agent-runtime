from __future__ import annotations

from typing import Any

from agent.agent_metrics import estimate_messages_chars
from agent.context_compaction import compact_context_references
from agent.model_streaming import consume_model_stream
from tools.tools import OPENAI_TOOLS


def normalize_message_for_api(message: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {'role': message['role']}

    if 'content' in message:
        payload['content'] = message['content']

    if message.get('role') == 'assistant' and message.get('tool_calls'):
        payload['tool_calls'] = message['tool_calls']
        payload['content'] = message.get('content')

    if message.get('role') == 'tool':
        payload['tool_call_id'] = message['tool_call_id']
        payload['content'] = message.get('content', '')

    return payload


def prepare_model_call(agent: Any, run_id: int) -> tuple[list[dict[str, Any]], int, int | None] | None:
    with agent.lock:
        if not agent._is_current_run(run_id):
            return None
        request_messages = [agent._normalize_message_for_api(dict(message)) for message in agent.messages]
        if request_messages and agent.request_system_prompt:
            request_messages[0]['content'] = agent.request_system_prompt
        turn_index = agent.loop_turn
        uncompacted_prompt_chars = estimate_messages_chars(request_messages)
        request_messages, compaction_stats = compact_context_references(request_messages)
        prompt_chars = estimate_messages_chars(request_messages)
        model_call_index = agent.metrics.start_model_call(
            run_id,
            turn_index,
            agent.model,
            prompt_chars,
            uncompacted_prompt_chars=uncompacted_prompt_chars,
            compaction_stats=compaction_stats,
        )
        if compaction_stats.get('context_reference_count'):
            agent._trace(
                'context_compaction_applied',
                turn=turn_index,
                original_prompt_chars=uncompacted_prompt_chars,
                compacted_prompt_chars=prompt_chars,
                saved_chars=compaction_stats.get('context_reference_saved_chars'),
                reference_count=compaction_stats.get('context_reference_count'),
                source_count=compaction_stats.get('context_reference_source_count'),
                aliases=compaction_stats.get('context_reference_aliases'),
                transforms=compaction_stats.get('context_reference_transforms'),
            )
        agent._trace(
            'model_call_started',
            turn=turn_index,
            model=agent.model,
            prompt_chars=prompt_chars,
            uncompacted_prompt_chars=uncompacted_prompt_chars,
            context_reference_saved_chars=compaction_stats.get('context_reference_saved_chars'),
            context_reference_count=compaction_stats.get('context_reference_count'),
            messages=agent.run_trace.payload(request_messages) if agent.run_trace else request_messages,
        )

    return request_messages, turn_index, model_call_index


def append_assistant_placeholder(agent: Any, run_id: int) -> dict[str, Any] | None:
    with agent.lock:
        if not agent._is_current_run(run_id):
            return None
        assistant_message: dict[str, Any] = {'role': 'assistant', 'content': ''}
        agent.messages.append(assistant_message)

    agent._notify_stream()
    return assistant_message


def finish_model_call(
    agent: Any,
    run_id: int,
    model_call_index: int | None,
    turn_index: int,
    assistant_message: dict[str, Any],
) -> dict[str, Any] | None:
    with agent.lock:
        if not agent._is_current_run(run_id):
            return None
        if assistant_message.get('tool_calls') and not assistant_message.get('content'):
            assistant_message['content'] = ''
        agent.metrics.finish_model_call(run_id, model_call_index)
        agent._trace(
            'model_call_finished',
            turn=turn_index,
            assistant_message=agent.run_trace.payload(assistant_message) if agent.run_trace else assistant_message,
        )

    agent._notify_stream()
    return dict(assistant_message)


def fail_model_call(
    agent: Any,
    run_id: int,
    model_call_index: int | None,
    turn_index: int,
    assistant_message: dict[str, Any],
    exc: Exception,
) -> dict[str, Any] | None:
    error_text = f'[Error: {exc}]'
    with agent.lock:
        if not agent._is_current_run(run_id):
            return None
        assistant_message.clear()
        assistant_message.update({'role': 'assistant', 'content': error_text})
        agent.last_error = str(exc)
        agent.metrics.finish_model_call(run_id, model_call_index)
        agent._trace('model_call_failed', turn=turn_index, error=str(exc))

    agent._notify_stream()
    return {'role': 'assistant', 'content': error_text}


def call_model_once(agent: Any, run_id: int) -> dict[str, Any] | None:
    prepared = agent._prepare_model_call(run_id)
    if prepared is None:
        return None
    request_messages, turn_index, model_call_index = prepared

    assistant_message = agent._append_assistant_placeholder(run_id)
    if assistant_message is None:
        return None

    try:
        stream = agent.client.chat.completions.create(
            model=agent.model,
            messages=request_messages,
            tools=OPENAI_TOOLS,
            temperature=0.1,
            stream=True,
        )

        if not consume_model_stream(agent, stream, run_id, model_call_index, assistant_message):
            return None
        return agent._finish_model_call(run_id, model_call_index, turn_index, assistant_message)

    except Exception as exc:
        return agent._fail_model_call(run_id, model_call_index, turn_index, assistant_message, exc)
