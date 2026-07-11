from __future__ import annotations

from pathlib import Path
from typing import Any

from system_prompt.system_prompt import build_request_system_prompt
from contracts.events import SkillPolicyEvent, SkillSelectionEvent, SkillSelectionEventStatus
from skills.intent import extract_intent


def skill_selection_event_status(value: object) -> SkillSelectionEventStatus:
    if value == SkillSelectionEventStatus.OK or value == SkillSelectionEventStatus.OK.value:
        return SkillSelectionEventStatus.OK
    if value == SkillSelectionEventStatus.ERROR or value == SkillSelectionEventStatus.ERROR.value:
        return SkillSelectionEventStatus.ERROR
    return SkillSelectionEventStatus.UNKNOWN


def latest_user_text(agent: Any) -> str:
    with agent.lock:
        for message in reversed(agent.messages):
            if message.get('role') == 'user':
                content = message.get('content')
                if isinstance(content, str):
                    return content
    return ''


def skill_selection_text_for_latest_user(agent: Any) -> str:
    user_text = agent._latest_user_text().strip()
    if agent.last_fulfilled_skill_name != 'owasp_security_review':
        return user_text

    intent = extract_intent(user_text)
    path = intent.get('args', {}).get('path')
    tokens = intent.get('tokens') or set()
    action = intent.get('action')
    if not isinstance(path, str) or not path:
        return user_text
    if action != 'review' and 'review' not in tokens and 'audit' not in tokens and 'inspect' not in tokens:
        return user_text
    if tokens & {'security', 'owasp', 'vulnerability', 'vulnerabilities', 'appsec'}:
        return user_text

    name = Path(path).name.lower()
    if name.startswith('security_') or name.startswith('security-'):
        return f'OWASP security review {path}'
    if user_text.lower().strip().startswith(('now review ', 'review ', 'audit ', 'inspect ')):
        return f'OWASP security review {path}'

    return user_text


def append_skill_selection_event(agent: Any, event: SkillSelectionEvent) -> None:
    agent.tool_events.append(event.to_payload())


def append_skill_policy_event(agent: Any, event: SkillPolicyEvent) -> None:
    agent.tool_events.append(event.to_payload())


def select_skill_for_current_request(agent: Any) -> dict[str, Any] | None:
    user_text = agent._latest_user_text().strip()
    if not user_text:
        return None
    selection_text = agent._skill_selection_text_for_latest_user()

    try:
        agent._trace('skill_selection_started', user_message=user_text, selection_text=selection_text)
        result = agent._request_skill_for_intent(selection_text)
    except Exception as exc:
        with agent.lock:
            agent._append_skill_selection_event(
                SkillSelectionEvent(
                    kind='skill_selection',
                    status='error',
                    error=str(exc),
                )
            )
            agent._trace('skill_selection_failed', error=str(exc))
        return None

    with agent.lock:
        agent._append_skill_selection_event(
            SkillSelectionEvent(
                kind='skill_selection',
                status=skill_selection_event_status(result.get('status')),
                skill_name=result.get('skill_name'),
                selection=result.get('selection'),
            )
        )
        agent._trace(
            'skill_selection_finished',
            status=result.get('status'),
            skill_name=result.get('skill_name'),
            result=agent.run_trace.payload(result) if agent.run_trace else result,
        )

    if result.get('status') != 'ok' or not result.get('skill_name'):
        return None
    return result


def configure_request_skill(agent: Any, run_id: int, selected_skill: dict[str, Any] | None) -> bool:
    with agent.lock:
        if not agent._is_current_run(run_id):
            return False
        agent.active_skill_selection = selected_skill
        agent._set_skill_state_from_selection(selected_skill or {})
        base_prompt = str(agent.messages[0].get('content', '')) if agent.messages else ''
        agent.request_system_prompt = build_request_system_prompt(base_prompt, selected_skill)
        if agent.metrics.current_request:
            agent.metrics.current_request['estimated_system_prompt_chars'] = len(agent.request_system_prompt)
        agent._trace(
            'request_system_prompt_built',
            active_skill_name=agent.active_skill_name,
            active_skill_selection=(
                agent.run_trace.payload(agent.active_skill_selection)
                if agent.run_trace
                else agent.active_skill_selection
            ),
            system_prompt_chars=len(agent.request_system_prompt),
            system_prompt=(
                agent.run_trace.payload(agent.request_system_prompt) if agent.run_trace else agent.request_system_prompt
            ),
        )

    return True
