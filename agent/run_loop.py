from __future__ import annotations

from typing import Any

from agent.agent_skill_policy import validate_final_response_against_skill_policy
from agent import model_lifecycle
from agent import skill_selection


def call_model(agent: Any, run_id: int | None = None) -> str | None:
    if run_id is None:
        run_id = agent._start_generation()
    if run_id is None:
        return None

    try:
        selected_skill = skill_selection.select_skill_for_current_request(agent)
        if not skill_selection.configure_request_skill(agent, run_id, selected_skill):
            return None

        for turn_index in range(0, agent.MAX_AUTO_TURNS):
            with agent.lock:
                if not agent._is_current_run(run_id):
                    return None
                agent.loop_turn = turn_index

            response = model_lifecycle.call_model_once(agent, run_id)
            if response is None:
                return None

            content = str(response.get('content') or '').strip()
            tool_calls = response.get('tool_calls') or []

            if tool_calls:
                for tool_call in tool_calls:
                    if not agent._execute_callable(tool_call, run_id):
                        return None
                continue

            if content == agent.DONE:
                with agent.lock:
                    if not agent._is_current_run(run_id):
                        return None
                    agent.messages.pop()
                    agent._trace('done_token_received')
                return content

            if content == '':
                with agent.lock:
                    if not agent._is_current_run(run_id):
                        return None
                    agent.messages.pop()
                    agent.last_error = 'Model returned an empty response.'
                    agent._trace('empty_model_response')
                if agent.active_skill_name:
                    agent._record_skill_event(agent.active_skill_name, 'failure')
                return None

            if agent.active_skill_name:
                policy_error = validate_final_response_against_skill_policy(agent, content)
                if policy_error is not None:
                    if agent._handle_skill_policy_blocked_final_response(run_id, content, policy_error):
                        continue
                    return None
                agent._record_skill_event(agent.active_skill_name, 'fulfilled')
                agent.last_fulfilled_skill_name = agent.active_skill_name
            else:
                agent.last_fulfilled_skill_name = None
            return content

        with agent.lock:
            if not agent._is_current_run(run_id):
                return None
            agent.last_error = f'Stopped after {agent.MAX_AUTO_TURNS} turns without receiving {agent.DONE}.'
            agent.messages.append({'role': 'assistant', 'content': agent.last_error})
            agent._trace('max_auto_turns_reached', max_auto_turns=agent.MAX_AUTO_TURNS)
        if agent.active_skill_name:
            agent._record_skill_event(agent.active_skill_name, 'failure')
        return None
    finally:
        agent._finish_generation(run_id)
