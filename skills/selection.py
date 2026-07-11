from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from contracts.skills import (
    RejectedSkillCandidate,
    SkillCandidate,
    SkillSelectionResult,
    SkillValidation,
)
from skills.intent import extract_intent
from skills.skills_registry import Skill
from skills.stats import get_skill_score_bonus, record_skill_event
from tools.skill_index_tools import search_skill_faiss_index


SKILL_AUTHORING_TOKENS = {
    'skill',
    'skills',
    'procedure',
    'procedures',
    'reusable',
    'register',
    'author',
}

MIN_TAG_OVERLAP_FOR_GENERIC_TRIGGER = 2
OWASP_SECURITY_REVIEW_SKILL = 'owasp_security_review'
SECURITY_AUDIT_TOKENS = {
    'appsec',
    'auth',
    'authentication',
    'authorization',
    'crypto',
    'cryptography',
    'injection',
    'owasp',
    'secret',
    'secrets',
    'security',
    'ssrf',
    'threat',
    'vulnerabilities',
    'vulnerability',
    'xss',
}
NON_AUDIT_ACTIONS = {'create', 'debug', 'edit', 'delete'}


def selection_result_payload(**fields: Any) -> dict[str, Any]:
    result = SkillSelectionResult(**fields)
    payload = result.to_payload()
    if result.skill_name is None:
        payload['skill_name'] = None
    return cast(dict[str, Any], payload)


def skill_validation_payload(validation: dict[str, Any], valid: bool = True) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        SkillValidation(
            valid=valid,
            score=validation.get('score'),
            reasons=list(validation.get('reasons') or []),
        ).to_payload(),
    )


def skill_candidate_payload(
    skill_name: str,
    *,
    score: float | None = None,
    distance: float | None = None,
    priority: int | None = None,
    forced: bool = False,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        SkillCandidate(
            skill_name=skill_name,
            score=score,
            distance=distance,
            priority=priority,
            forced=forced,
        ).to_payload(),
    )


def rejected_skill_candidate_payload(
    skill_name: str,
    reason: str,
    *,
    score: float | None = None,
    distance: float | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        RejectedSkillCandidate(
            skill_name=skill_name,
            reason=reason,
            score=score,
            distance=distance,
        ).to_payload(),
    )


# Selection combines FAISS retrieval, syntax checks, heuristic scoring, and
# historical skill feedback into one ranked skill choice.
def is_explicit_skill_authoring_intent(intent: dict[str, Any]) -> bool:
    tokens: set[str] = intent['tokens']
    return bool(tokens & SKILL_AUTHORING_TOKENS)


def is_explicit_owasp_security_audit_intent(intent: dict[str, Any]) -> bool:
    tokens: set[str] = intent['tokens']
    action: str = intent['action']

    if action in NON_AUDIT_ACTIONS or tokens & {'fix', 'repair', 'patch'}:
        return False
    if not (tokens & SECURITY_AUDIT_TOKENS):
        return False
    return action == 'review' or bool(tokens & {'audit', 'review', 'inspect', 'owasp'})


def forced_owasp_security_review_choice(
    skills_by_name: dict[str, Skill],
    user_text: str,
    arguments: dict[str, Any],
) -> dict[str, Any] | None:
    intent = extract_intent(user_text)
    if not is_explicit_owasp_security_audit_intent(intent):
        return None

    skill = skills_by_name.get(OWASP_SECURITY_REVIEW_SKILL)
    if skill is None:
        return selection_result_payload(
            status='ok',
            skill_name=None,
            selection_reason='owasp security audit requested but owasp_security_review is not loaded',
            message='OWASP security audit was requested, but the OWASP security review skill is not available.',
        )

    ok, syntax_error = validate_skill_syntax(skill, arguments)
    if not ok:
        return selection_result_payload(
            status='ok',
            skill_name=None,
            selection_reason='owasp security audit requested but required arguments are missing',
            message=f'OWASP security audit requires valid arguments: {syntax_error}.',
            rejected_candidates=[
                rejected_skill_candidate_payload(skill.name, str(syntax_error)),
            ],
        )

    score, validation = score_skill_choice(skill, user_text, arguments)
    validation['reasons'].append('forced_owasp_security_audit_intent')
    record_skill_event(skill.name, 'selected')
    return selection_result_payload(
        status='ok',
        skill_name=skill.name,
        validation=skill_validation_payload(validation),
        distance=0.0,
        forced=True,
        candidates=[
            skill_candidate_payload(skill.name, score=score, distance=0.0, forced=True),
        ],
    )


def skill_has_lexical_trigger(skill: Skill, intent: dict[str, Any]) -> bool:
    tokens: set[str] = intent['tokens']
    action: str = intent['action']
    filetype: str | None = intent['filetype']
    domain: str = intent['domain']

    if skill.category == 'skills':
        return is_explicit_skill_authoring_intent(intent)

    if action != 'unknown' and action in skill.supported_actions:
        return True

    if filetype and filetype in skill.supported_filetypes and tokens & skill.tags:
        return True

    if domain != 'general' and (skill.category == domain or domain in skill.supported_domains):
        return bool(tokens & skill.tags)

    return len(tokens & skill.tags) >= MIN_TAG_OVERLAP_FOR_GENERIC_TRIGGER


def validate_skill_syntax(skill: Skill, arguments: dict[str, Any]) -> tuple[bool, str | None]:
    required = set(skill.parameters.get('required', []))
    missing = sorted(required - set(arguments.keys()))
    if missing:
        return False, f"missing required argument(s): {', '.join(missing)}"

    if skill.parameters.get('additionalProperties') is False:
        allowed = set(skill.parameters.get('properties', {}).keys())
        unexpected = sorted(set(arguments.keys()) - allowed)
        if unexpected:
            return False, f"unexpected arguments: {', '.join(unexpected)}"

    properties = skill.parameters.get('properties', {})
    for arg_name, value in arguments.items():
        expected_type = properties.get(arg_name, {}).get('type')
        if expected_type == 'string' and not isinstance(value, str):
            return False, f"argument '{arg_name}' must be a string"

    return True, None


def score_skill_choice(skill: Skill, user_text: str, arguments: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    intent = extract_intent(user_text)
    tokens: set[str] = intent['tokens']
    action: str = intent['action']
    domain: str = intent['domain']
    filetype: str | None = intent['filetype']
    speech_act: str = intent['speech_act']

    score = 0.0
    reasons: list[str] = []

    if speech_act == 'question':
        score -= 10.0
        reasons.append('question_penalty')
    elif speech_act == 'mixed':
        score -= 4.0
        reasons.append('mixed_question_penalty')

    if skill.category == 'skills' and not (tokens & SKILL_AUTHORING_TOKENS):
        score -= 12.0
        reasons.append('missing_skill_authoring_language_penalty')

    overlap = len(skill.tags & tokens)
    if overlap:
        score += 2.0 * overlap
        reasons.append(f'tag_overlap={overlap}')

    if action != 'unknown' and action in skill.supported_actions:
        score += 4.0
        reasons.append('action_match')
    elif action != 'unknown' and skill.supported_actions:
        score -= 12.0
        reasons.append('action_mismatch')
    elif action == 'review':
        score -= 6.0
        reasons.append('review_action_mismatch')

    if skill.category == domain or domain in skill.supported_domains:
        score += 3.0
        reasons.append('domain_match')

    if filetype and filetype in skill.supported_filetypes:
        score += 3.0
        reasons.append('filetype_match')

    if all(arg in arguments for arg in skill.required_args):
        score += 2.0
        reasons.append('required_args_present')

    score += 8.0 * skill.default_score
    score += 0.02 * skill.priority
    score += 0.02 * skill.specificity

    history_bonus = get_skill_score_bonus(skill.name)
    if history_bonus:
        score += history_bonus
        reasons.append(f'history_bonus={history_bonus:.2f}')

    validation = {
        'intent': {
            **intent,
            'tokens': sorted(intent['tokens']),
        },
        'score': score,
        'reasons': reasons,
    }
    return score, validation


def build_retrieval_query(user_text: str, arguments: dict[str, Any]) -> str:
    intent = extract_intent(user_text)
    parts = [user_text.strip()]

    if intent['action'] != 'unknown':
        parts.append(f'action: {intent["action"]}')
    if intent['domain'] != 'general':
        parts.append(f'domain: {intent["domain"]}')
    if intent['filetype']:
        parts.append(f'filetype: {intent["filetype"]}')

    path = arguments.get('path')
    if isinstance(path, str) and path.strip():
        suffix = Path(path).suffix.lower().lstrip('.')
        if suffix:
            parts.append(f'target filetype: {suffix}')
        parts.append('target is a sandbox file path')

    symbol = arguments.get('symbol')
    if isinstance(symbol, str) and symbol.strip():
        parts.append('target includes a specific symbol or method')

    return ' | '.join(part for part in parts if part)


def retrieve_skill_candidates(
    skills_by_name: dict[str, Skill],
    user_text: str,
    arguments: dict[str, Any],
    k: int = 8,
) -> list[tuple[Skill, dict[str, Any]]]:
    intent = extract_intent(user_text)
    if not any(skill_has_lexical_trigger(skill, intent) for skill in skills_by_name.values()):
        return []

    query = build_retrieval_query(user_text, arguments)
    result = search_skill_faiss_index(query=query, k=k)
    if result.get('status') != 'ok':
        return []

    grouped: dict[str, dict[str, Any]] = {}
    for match in result.get('matches', []):
        skill_name = match.get('skill_name')
        if not skill_name:
            continue
        current = grouped.get(skill_name)
        if current is None or float(match.get('distance', 1e9)) < float(current.get('distance', 1e9)):
            grouped[skill_name] = match

    candidates: list[tuple[Skill, dict[str, Any]]] = []
    for skill_name, match in sorted(grouped.items(), key=lambda item: float(item[1].get('distance', 1e9))):
        skill = skills_by_name.get(skill_name)
        if skill is None:
            continue
        record_skill_event(skill_name, 'retrieved')
        candidates.append((skill, match))

    return candidates


def choose_skill_for_intent(
    skills_by_name: dict[str, Skill],
    user_text: str,
    arguments: dict[str, Any],
    *,
    k: int = 8,
    threshold: float = 8.0,
) -> dict[str, Any]:
    forced_choice = forced_owasp_security_review_choice(skills_by_name, user_text, arguments)
    if forced_choice is not None:
        return forced_choice

    candidates = retrieve_skill_candidates(skills_by_name, user_text, arguments, k=k)
    if not candidates:
        return selection_result_payload(
            status='ok',
            skill_name=None,
            selection_reason='no relevant skill candidates found',
            message='No relevant skill is available. Improvise a short procedure with normal tool discipline.',
        )

    ranked: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    intent = extract_intent(user_text)
    for skill, match in candidates:
        if skill.name == OWASP_SECURITY_REVIEW_SKILL and not is_explicit_owasp_security_audit_intent(intent):
            rejected.append(
                rejected_skill_candidate_payload(
                    skill.name,
                    'missing explicit OWASP/security audit intent',
                    distance=float(match.get('distance', 1e9)),
                )
            )
            continue

        if skill.category == 'skills' and not is_explicit_skill_authoring_intent(intent):
            rejected.append(
                rejected_skill_candidate_payload(
                    skill.name,
                    'missing explicit skill-authoring intent',
                    distance=float(match.get('distance', 1e9)),
                )
            )
            continue

        ok, syntax_error = validate_skill_syntax(skill, arguments)
        if not ok:
            rejected.append(
                rejected_skill_candidate_payload(
                    skill.name,
                    str(syntax_error),
                    distance=float(match.get('distance', 1e9)),
                )
            )
            continue

        score, validation = score_skill_choice(skill, user_text, arguments)

        ranked.append({
            'skill': skill,
            'score': score,
            'distance': float(match.get('distance', 1e9)),
            'match': match,
            'validation': validation,
        })

    if not ranked:
        return selection_result_payload(
            status='ok',
            skill_name=None,
            selection_reason='no skill candidates passed validation',
            message='No relevant skill is available. Improvise a short procedure with normal tool discipline.',
            rejected_candidates=rejected[:5],
        )

    ranked.sort(key=lambda item: (-item['score'], item['distance']))
    best = ranked[0]

    if best['score'] < threshold:
        return selection_result_payload(
            status='ok',
            skill_name=None,
            selection_reason='best skill below threshold',
            message='No relevant skill is available. Improvise a short procedure with normal tool discipline.',
            best_candidate=skill_candidate_payload(
                best['skill'].name,
                score=best['score'],
                distance=best['distance'],
            ),
            candidates=[
                skill_candidate_payload(
                    item['skill'].name,
                    score=item['score'],
                    distance=item['distance'],
                )
                for item in ranked[:5]
            ],
        )

    record_skill_event(best['skill'].name, 'selected')
    return selection_result_payload(
        status='ok',
        skill_name=best['skill'].name,
        validation=skill_validation_payload(best['validation']),
        distance=best['distance'],
        candidates=[
            skill_candidate_payload(
                item['skill'].name,
                score=item['score'],
                distance=item['distance'],
            )
            for item in ranked[:5]
        ],
    )
