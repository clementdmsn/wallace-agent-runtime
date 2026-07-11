from __future__ import annotations

from typing import Any

from contracts.events import SkillPolicyEvent


def handle_skill_policy_blocked_final_response(
    agent: Any,
    run_id: int,
    content: str,
    policy_error: dict[str, Any],
) -> bool:
    with agent.lock:
        if not agent._is_current_run(run_id):
            return False
        if agent.messages and agent.messages[-1].get('role') == 'assistant':
            agent.messages.pop()
        agent.messages.append({
            'role': 'system',
            'content': (
                'Runtime skill policy blocked the previous final answer.\n'
                f'{policy_error["message"]}\n'
                'Do not cite OWASP from memory. Do not provide a final answer until the required tool succeeds.'
            ),
        })
        agent._append_skill_policy_event(
            SkillPolicyEvent(
                kind='skill_policy',
                status='error',
                error=policy_error.get('error'),
                message=policy_error.get('message'),
                required_tool=policy_error.get('required_tool'),
            )
        )
        agent._trace(
            'skill_policy_blocked_final_response',
            error=policy_error.get('error'),
            required_tool=policy_error.get('required_tool'),
            blocked_content_chars=len(content),
        )
    if agent.active_skill_name:
        agent._record_skill_event(agent.active_skill_name, 'failure')
    agent._notify_stream()
    return True
