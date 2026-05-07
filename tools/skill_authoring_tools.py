import json
from pathlib import Path
import re
from typing import Any

from config import SETTINGS
from sandbox import configured_project_path, project_relative_path, safe_path
from skills.intent import extract_intent
from tools.skill_index_tools import create_skill_faiss_index, rebuild_skill_faiss_index

REQUIRED_SKILL_METADATA_FIELDS = {
    'name',
    'summary',
    'description',
    'categories',
    'when_to_use',
    'when_not_to_use',
    'trigger_actions',
    'inputs',
    'outputs',
    'tools_required',
}

OPTIONAL_SKILL_METADATA_FIELDS = {
    'skill_id',
    'exclusions',
    'examples',
    'preconditions',
    'default_score',
}

ALLOWED_SKILL_METADATA_FIELDS = REQUIRED_SKILL_METADATA_FIELDS | OPTIONAL_SKILL_METADATA_FIELDS

KNOWN_RUNTIME_INPUTS = {'path', 'symbol', 'language', 'query'}
KNOWN_TOOL_NAMES = {
    'run_shell',
    'read_file',
    'read_file_with_line_numbers',
    'write_file',
    'replace_in_file',
    'append_to_file',
    'find_file',
    'summarize_code_file',
    'list_code_symbols',
    'explain_function_for_model',
    'create_skill_faiss_index',
    'discover_review_targets',
    'search_skill_faiss_index',
    'search_owasp_reference',
    'rebuild_skill_faiss_index',
    'rebuild_owasp_reference_index',
    'validate_owasp_corpus',
    'create_skill',
    'finalize_skill_draft',
    'repair_skill_draft',
    'remove_file',
}
CODE_CATEGORIES = {'code', 'code_analysis', 'python', 'javascript', 'typescript'}
CODE_MUTATION_WORDS = ('create', 'edit', 'refactor', 'fix', 'debug', 'review', 'test')
PATH_HINT = 'Use an explicit extractable path like ./snake_game, snake_game/, src/app.py, or add a query input and resolve it with find_file.'


def active_skill_metadata_dir() -> Path:
    return configured_project_path(getattr(SETTINGS, 'skill_metadata_dir', 'skill_catalog/metadatas'))


def active_skill_procedure_dir() -> Path:
    return configured_project_path(getattr(SETTINGS, 'skill_procedure_dir', 'skill_catalog/procedures'))


def _string_list(payload: dict[str, Any], field: str) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def instruction_style_text(text: str) -> str:
    cleaned = ' '.join(text.strip().rstrip('?').split())
    lowered = cleaned.lower()
    replacements = [
        (r'^how is (?:this|the) code organized$', 'analyze code organization'),
        (r'^what are the main directories$', 'identify main directories'),
        (r'^what does (?:this|it) do$', 'explain what this does'),
        (r'^where is (.+)$', r'find \1'),
    ]
    for pattern, replacement in replacements:
        if re.match(pattern, lowered):
            return re.sub(pattern, replacement, lowered)

    question_prefixes = (
        'how do i ',
        'how can i ',
        'how to ',
        'what is ',
        'what are ',
        'where is ',
        'where are ',
        'why does ',
        'when should ',
    )
    for prefix in question_prefixes:
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix):]
            break
    return lowered.strip() or cleaned


def example_with_path(text: str) -> str:
    base = instruction_style_text(text)
    if re.search(r'(?:^|[\s:])(?:\.{1,2}/|/|\w[\w.-]*/|\w+\.\w+)', base):
        return base
    return f'{base} at ./example_project'


def schema_object_for_value(name: str, value: Any) -> dict[str, str] | None:
    if isinstance(value, dict):
        if isinstance(value.get('type'), str):
            schema = dict(value)
            schema.setdefault('description', f'{name.replace("_", " ").title()}.')
            return schema
        return None
    if isinstance(value, str):
        if value in {'string', 'number', 'integer', 'boolean', 'object', 'array'}:
            return {'type': value, 'description': f'{name.replace("_", " ").title()}.'}
        return {'type': 'string', 'description': value}
    return None


def normalize_skill_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = dict(payload)
    normalizations: list[dict[str, Any]] = []

    if 'examples' not in normalized or not _string_list(normalized, 'examples'):
        source = _string_list(normalized, 'trigger_actions') or _string_list(normalized, 'when_to_use')
        examples = [instruction_style_text(item) for item in source if instruction_style_text(item)]
        if examples:
            normalized['examples'] = examples[:3]
            normalizations.append({
                'field': 'examples',
                'action': 'derived_from_routing_text',
                'value': normalized['examples'],
            })

    for field in ('when_to_use', 'trigger_actions', 'examples'):
        values = _string_list(normalized, field)
        if not values:
            continue
        repaired = [instruction_style_text(item) if '?' in item else item for item in values]
        if repaired != values:
            normalized[field] = repaired
            normalizations.append({
                'field': field,
                'action': 'converted_questions_to_instruction_text',
                'before': values,
                'after': repaired,
            })

    for field in ('inputs', 'outputs'):
        value = normalized.get(field)
        if not isinstance(value, dict):
            continue
        repaired: dict[str, Any] = {}
        changed = False
        for key, item in value.items():
            schema = schema_object_for_value(str(key), item)
            if schema is None:
                repaired[key] = item
                continue
            repaired[key] = schema
            changed = changed or schema != item
        if changed:
            normalized[field] = repaired
            normalizations.append({
                'field': field,
                'action': 'converted_values_to_schema_objects',
            })

    categories = {item.lower() for item in _string_list(normalized, 'categories')}
    if categories & CODE_CATEGORIES:
        exclusions = _string_list(normalized, 'exclusions')
        joined_exclusions = ' '.join(_string_list(normalized, 'when_not_to_use') + exclusions).lower()
        trigger_text = ' '.join(_string_list(normalized, 'trigger_actions') + _string_list(normalized, 'when_to_use')).lower()
        missing = [
            word for word in CODE_MUTATION_WORDS
            if word not in joined_exclusions and word not in trigger_text
        ]
        if missing:
            normalized['exclusions'] = exclusions + missing
            normalizations.append({
                'field': 'exclusions',
                'action': 'added_missing_code_task_false_positives',
                'added': missing,
            })

    return normalized, normalizations


def probe_skill_routing(payload: dict[str, Any]) -> dict[str, Any]:
    inputs = payload.get('inputs') if isinstance(payload.get('inputs'), dict) else {}
    required_args = sorted(key for key in inputs if key in KNOWN_RUNTIME_INPUTS)
    examples = _string_list(payload, 'examples')
    probes: list[dict[str, Any]] = []

    for example in examples:
        intent = extract_intent(example)
        probes.append({
            'text': example,
            'extracted_args': intent.get('args', {}),
        })

    satisfied_args = sorted({
        arg
        for probe in probes
        for arg in required_args
        if arg in probe.get('extracted_args', {})
    })
    missing_args = [arg for arg in required_args if arg not in satisfied_args]

    return {
        'required_args': required_args,
        'satisfied_args': satisfied_args,
        'missing_args': missing_args,
        'probes': probes,
        'status': 'ok' if not missing_args else 'error',
    }


def validate_skill_routing_contract(payload: dict[str, Any]) -> list[dict[str, Any]]:
    report = probe_skill_routing(payload)
    missing_args = report['missing_args']
    if not missing_args:
        return []

    errors: list[dict[str, Any]] = []
    for missing_arg in missing_args:
        hint = PATH_HINT if missing_arg == 'path' else f'Use an example that lets the runtime extract {missing_arg}, or remove the required input.'
        errors.append({
            'field': 'examples',
            'message': f'required input {missing_arg} is not extractable from example requests',
            'value': {
                'missing_runtime_args': [missing_arg],
                'required_args': report['required_args'],
                'probes': report['probes'],
                'hint': hint,
            },
        })
    return errors


def _metadata_field_error(payload: dict[str, Any], **extra: Any) -> dict[str, Any] | None:
    missing = sorted(field for field in REQUIRED_SKILL_METADATA_FIELDS if field not in payload)
    if missing:
        return {
            'status': 'error',
            'error': 'json_payload missing required skill metadata fields',
            'missing_fields': missing,
            **extra,
        }

    unexpected = sorted(field for field in payload if field not in ALLOWED_SKILL_METADATA_FIELDS)
    if unexpected:
        return {
            'status': 'error',
            'error': 'json_payload contains unknown skill metadata fields',
            'unexpected_fields': unexpected,
            **extra,
        }

    return None


def validate_skill_payload(markdown: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

    def add(field: str, message: str, value: Any = None) -> None:
        error = {'field': field, 'message': message}
        if value is not None:
            error['value'] = value
        errors.append(error)

    for field in ('categories', 'when_to_use', 'when_not_to_use', 'trigger_actions', 'tools_required'):
        if not isinstance(payload.get(field), list) or not all(isinstance(item, str) for item in payload.get(field, [])):
            add(field, 'must be an array of strings')

    if not isinstance(payload.get('inputs'), dict):
        add('inputs', 'must be an object')
    if not isinstance(payload.get('outputs'), dict):
        add('outputs', 'must be an object')

    inputs = payload.get('inputs') if isinstance(payload.get('inputs'), dict) else {}
    invalid_input_schemas = sorted(
        key for key, value in inputs.items()
        if not isinstance(value, dict) or not isinstance(value.get('type'), str)
    )
    if invalid_input_schemas:
        add(
            'inputs',
            'each input must be a schema object with a type',
            {'invalid_inputs': invalid_input_schemas},
        )

    outputs = payload.get('outputs') if isinstance(payload.get('outputs'), dict) else {}
    invalid_output_schemas = sorted(
        key for key, value in outputs.items()
        if not isinstance(value, dict) or not isinstance(value.get('type'), str)
    )
    if invalid_output_schemas:
        add(
            'outputs',
            'each output must be a schema object with a type',
            {'invalid_outputs': invalid_output_schemas},
        )

    when_not_to_use = _string_list(payload, 'when_not_to_use')
    if not when_not_to_use:
        add('when_not_to_use', 'must include at least one close-but-wrong case')

    examples = _string_list(payload, 'examples')
    if not examples:
        add('examples', 'must include at least one example request')

    question_like: list[dict[str, str]] = []
    for field in ('when_to_use', 'trigger_actions', 'examples'):
        for item in _string_list(payload, field):
            if '?' in item:
                question_like.append({'field': field, 'text': item})
    if question_like:
        add(
            'routing_text',
            'routing examples and trigger text must be instruction-style, not question-shaped',
            question_like,
        )

    unknown_inputs = sorted(key for key in inputs if key not in KNOWN_RUNTIME_INPUTS)
    if unknown_inputs:
        add(
            'inputs',
            'input keys must match runtime-extracted argument names',
            {'unknown_inputs': unknown_inputs, 'allowed_inputs': sorted(KNOWN_RUNTIME_INPUTS)},
        )

    tools_required = _string_list(payload, 'tools_required')
    unknown_tools = sorted(tool for tool in tools_required if tool not in KNOWN_TOOL_NAMES)
    if unknown_tools:
        add(
            'tools_required',
            'contains tools that are not registered',
            {'unknown_tools': unknown_tools, 'allowed_tools': sorted(KNOWN_TOOL_NAMES)},
        )

    markdown_lower = markdown.lower()
    missing_tool_mentions = sorted(tool for tool in tools_required if tool.lower() not in markdown_lower)
    if missing_tool_mentions:
        add(
            'markdown',
            'procedure must explicitly mention every required tool',
            {'missing_tool_mentions': missing_tool_mentions},
        )

    categories = {item.lower() for item in _string_list(payload, 'categories')}
    is_skill_authoring = 'skills' in categories
    default_score = payload.get('default_score', 0.5)
    try:
        default_score_value = float(default_score)
    except Exception:
        add('default_score', 'must be a number when provided', default_score)
        default_score_value = 0.5
    else:
        if default_score_value < 0 or default_score_value > 1:
            add('default_score', 'must be between 0.0 and 1.0', default_score)
        elif default_score_value > 0.7 and not is_skill_authoring:
            add('default_score', 'must be 0.7 or lower unless the skill is narrowly for skill authoring', default_score)

    if categories & CODE_CATEGORIES:
        joined_exclusions = ' '.join(when_not_to_use + _string_list(payload, 'exclusions')).lower()
        missing_words = [word for word in CODE_MUTATION_WORDS if word not in joined_exclusions]
        trigger_text = ' '.join(_string_list(payload, 'trigger_actions') + _string_list(payload, 'when_to_use')).lower()
        intended_words = {word for word in CODE_MUTATION_WORDS if word in trigger_text}
        required_exclusion_words = [word for word in missing_words if word not in intended_words]
        if required_exclusion_words:
            add(
                'when_not_to_use',
                'code skills must exclude nearby code task types they do not handle',
                {'missing_exclusions': required_exclusion_words},
            )

    if tools_required and not any(word in markdown_lower for word in ('fail', 'fails', 'failure', 'missing', 'error')):
        add('markdown', 'procedure must include fallback or failure behavior')

    return errors


def build_repair_instructions(errors: list[dict[str, Any]]) -> list[str]:
    instructions: list[str] = []
    for error in errors:
        field = error.get('field')
        if field == 'routing_text':
            instructions.append('Use instruction-style routing text; remove question-shaped triggers/examples.')
        elif field == 'inputs':
            instructions.append('Use runtime input keys only and schema objects, e.g. "path": {"type": "string", "description": "..."}')
        elif field == 'outputs':
            instructions.append('Use schema objects for outputs, e.g. "summary": {"type": "string", "description": "..."}')
        elif field == 'tools_required':
            instructions.append('Use only registered tool names.')
        elif field == 'markdown':
            instructions.append('Mention every required tool by exact name and include fallback/failure behavior.')
        elif field == 'default_score':
            instructions.append('Use default_score between 0.4 and 0.7 unless this is a narrow skill-authoring skill.')
        elif field == 'when_not_to_use':
            value = error.get('value') if isinstance(error.get('value'), dict) else {}
            missing = value.get('missing_exclusions', [])
            if missing:
                instructions.append(
                    'Add the missing code-task false positives to metadata when_not_to_use or exclusions: '
                    + ', '.join(str(item) for item in missing)
                    + '. These words must be in the JSON metadata, not only the markdown procedure.'
                )
            else:
                instructions.append(
                    'Add close false positives to metadata when_not_to_use or exclusions; code skills must exclude '
                    'create/edit/refactor/fix/debug/review/test unless handled.'
                )
        elif field == 'examples':
            value = error.get('value') if isinstance(error.get('value'), dict) else {}
            missing = value.get('missing_runtime_args', [])
            hint = value.get('hint')
            if missing:
                instructions.append(
                    'Add at least one instruction-style example that exposes required runtime input(s): '
                    + ', '.join(str(item) for item in missing)
                    + (f'. {hint}' if isinstance(hint, str) else '.')
                )
            else:
                instructions.append('Add at least one instruction-style example request.')
        else:
            instructions.append(f"Fix {field}: {error.get('message', 'invalid value')}")

    return list(dict.fromkeys(instructions))


def build_repair_suggestions(errors: list[dict[str, Any]], payload: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []

    inputs = payload.get('inputs') if isinstance(payload.get('inputs'), dict) else {}
    for error in errors:
        field = error.get('field')
        value = error.get('value') if isinstance(error.get('value'), dict) else {}

        if field == 'inputs':
            for key in value.get('unknown_inputs', []):
                if key in {'file_path', 'filepath', 'function_path', 'source_path'}:
                    suggestions.append({
                        'field': 'inputs',
                        'replace': key,
                        'with': 'path',
                        'reason': 'File paths must use the runtime input key path.',
                    })
            if 'function' in str(payload.get('name', '')).lower() and 'symbol' not in inputs:
                suggestions.append({
                    'field': 'inputs',
                    'add': 'symbol',
                    'schema': {
                        'type': 'string',
                        'description': 'Function or method name to inspect.',
                    },
                    'reason': 'Function-level skills should use symbol for the function name.',
                })

        if field == 'examples':
            missing_args = value.get('missing_runtime_args', [])
            if 'path' in missing_args:
                suggestions.append({
                    'field': 'examples',
                    'set': [example_with_path(item) for item in _string_list(payload, 'examples')],
                    'reason': 'At least one example must contain an extractable path for the required path input.',
                })
                continue

            source = _string_list(payload, 'trigger_actions') or _string_list(payload, 'when_to_use')
            examples = [instruction_style_text(item) for item in source if instruction_style_text(item)]
            if examples:
                suggestions.append({
                    'field': 'examples',
                    'set': examples[:3],
                    'reason': 'Examples are required for retrieval and can be derived from instruction-style routing text.',
                })

        if field == 'routing_text':
            for item in error.get('value', []) if isinstance(error.get('value'), list) else []:
                if not isinstance(item, dict):
                    continue
                target_field = item.get('field')
                text = item.get('text')
                if isinstance(target_field, str) and isinstance(text, str):
                    suggestions.append({
                        'field': target_field,
                        'replace': text,
                        'with': instruction_style_text(text),
                        'reason': 'Routing text must be instruction-style, not question-shaped.',
                    })

        if field == 'when_not_to_use':
            missing = value.get('missing_exclusions', [])
            if missing:
                suggestions.append({
                    'field': 'when_not_to_use',
                    'add_terms': missing,
                    'reason': 'Code skills must name nearby task types they do not handle.',
                })

    return suggestions


def apply_structured_repairs(payload: dict[str, Any], repairs: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    repaired = dict(payload)
    applied: list[dict[str, Any]] = []

    for repair in repairs:
        if not isinstance(repair, dict):
            continue
        field = repair.get('field')
        if not isinstance(field, str):
            continue

        if 'set' in repair:
            repaired[field] = repair['set']
            applied.append({'field': field, 'action': 'set'})
            continue

        if 'add_terms' in repair:
            terms = repair.get('add_terms')
            if not isinstance(terms, list):
                continue
            current = _string_list(repaired, field)
            additions = [str(term) for term in terms if str(term) not in ' '.join(current).lower()]
            repaired[field] = current + additions
            applied.append({'field': field, 'action': 'add_terms', 'added': additions})
            continue

        if 'replace' in repair and 'with' in repair:
            current = repaired.get(field)
            if isinstance(current, list):
                before = str(repair['replace'])
                after = str(repair['with'])
                replaced = [after if item == before else item for item in current]
                if replaced != current:
                    repaired[field] = replaced
                    applied.append({'field': field, 'action': 'replace', 'replace': before, 'with': after})
            elif isinstance(current, dict):
                before = str(repair['replace'])
                after = str(repair['with'])
                if before in current:
                    current = dict(current)
                    current[after] = current.pop(before)
                    repaired[field] = current
                    applied.append({'field': field, 'action': 'rename_key', 'replace': before, 'with': after})
            continue

        if 'add' in repair:
            current = repaired.get(field)
            if isinstance(current, dict):
                key = str(repair['add'])
                schema = repair.get('schema')
                if key not in current and isinstance(schema, dict):
                    current = dict(current)
                    current[key] = schema
                    repaired[field] = current
                    applied.append({'field': field, 'action': 'add_schema', 'add': key})

    return repaired, applied


def safe_skill_title(title: str) -> str:
    safe_title = title.strip().lower()
    safe_title = ''.join(c if c.isalnum() else '_' for c in safe_title)
    safe_title = '_'.join(part for part in safe_title.split('_') if part)
    return safe_title


def write_skill_draft(
    safe_title: str,
    markdown: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    draft_dir = safe_path('skills/drafts')
    draft_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = draft_dir / f'{safe_title}.json'
    procedure_path = draft_dir / f'{safe_title}.md'
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    procedure_path.write_text(markdown.rstrip() + '\n', encoding='utf-8')

    return {
        'draft_id': safe_title,
        'draft_metadata_path': metadata_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
        'draft_procedure_path': procedure_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
    }


def validation_failure_result(
    validation_errors: list[dict[str, Any]],
    markdown: str,
    payload: dict[str, Any],
    safe_title: str,
    normalizations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    draft = write_skill_draft(safe_title, markdown, payload)
    return {
        'status': 'error',
        'error': 'json_payload failed skill quality validation',
        'message': (
            'Draft files were written under skills/drafts only. Repair the draft files with replace_in_file, '
            'then call finalize_skill_draft. Do not edit active skill catalog files directly.'
        ),
        'validation_errors': validation_errors,
        'repair_instructions': build_repair_instructions(validation_errors),
        'repair_suggestions': build_repair_suggestions(validation_errors, payload),
        'normalizations': normalizations or [],
        'retry_policy': (
            'Prefer repair_skill_draft with repair_suggestions for metadata errors. '
            'Revise only rejected draft fields and preserve valid fields. '
            'After 3 failed finalize attempts, stop and show the latest draft paths and errors to the user.'
        ),
        **draft,
    }


def create_skill(
    title: str,
    markdown: str,
    json_payload: dict[str, Any],
    rebuild_index: bool = True,
) -> dict[str, Any]:
    try:
        if not isinstance(title, str) or not title.strip():
            return {'status': 'error', 'error': 'title must be a non-empty string'}

        if not isinstance(markdown, str) or not markdown.strip():
            return {'status': 'error', 'error': 'markdown must be a non-empty string'}

        if not isinstance(json_payload, dict):
            return {'status': 'error', 'error': 'json_payload must be an object'}

        safe_title = safe_skill_title(title)

        if not safe_title:
            return {'status': 'error', 'error': 'title produced an empty safe filename'}

        payload = dict(json_payload)

        skill_name = payload.get('name') or f'skill_{safe_title}'
        skill_id = payload.get('skill_id') or skill_name

        payload['name'] = str(skill_name)
        payload['skill_id'] = str(skill_id)
        payload, normalizations = normalize_skill_payload(payload)

        field_error = _metadata_field_error(payload)
        if field_error:
            if normalizations:
                field_error['normalizations'] = normalizations
            return field_error

        validation_errors = validate_skill_payload(markdown, payload)
        validation_errors.extend(validate_skill_routing_contract(payload))
        if validation_errors:
            return validation_failure_result(validation_errors, markdown, payload, safe_title, normalizations)

        metadata_dir = active_skill_metadata_dir()
        procedure_dir = active_skill_procedure_dir()

        metadata_dir.mkdir(parents=True, exist_ok=True)
        procedure_dir.mkdir(parents=True, exist_ok=True)

        metadata_path = metadata_dir / f'{safe_title}.json'
        procedure_path = procedure_dir / f'{safe_title}.md'

        metadata_rel = project_relative_path(metadata_path)
        procedure_rel = project_relative_path(procedure_path)

        if metadata_path.exists() or procedure_path.exists():
            return {
                'status': 'error',
                'error': 'skill already exists',
                'metadata_path': metadata_rel,
                'procedure_path': procedure_rel,
            }

        metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

        procedure_path.write_text(
            markdown.rstrip() + '\n',
            encoding='utf-8',
        )

        # New skill files are durable before indexing so partial failures are
        # visible to the user instead of silently losing authored content.
        if rebuild_index:
            all_metadata_paths = [
                project_relative_path(path)
                for path in sorted(metadata_dir.glob('*.json'))
            ]
            index_result = rebuild_skill_faiss_index(all_metadata_paths)
        else:
            index_result = create_skill_faiss_index(metadata_rel)

        if not isinstance(index_result, dict) or index_result.get('status') != 'ok':
            return {
                'status': 'error',
                'error': 'skill files were written, but index update failed',
                'skill_name': payload['name'],
                'metadata_path': metadata_rel,
                'procedure_path': procedure_rel,
                'index_result': index_result,
            }

        try:
            from skills import skills as skills_module

            skills_module.refresh_skill_registry()
            registry_reloaded = True
        except Exception as exc:
            registry_reloaded = False
            registry_reload_error = str(exc)
        else:
            registry_reload_error = None

        result = {
            'status': 'ok',
            'skill_name': payload['name'],
            'skill_id': payload['skill_id'],
            'metadata_path': metadata_rel,
            'procedure_path': procedure_rel,
            'index_result': index_result,
            'registry_reloaded': registry_reloaded,
            'message': 'skill added and skill index updated',
        }
        if normalizations:
            result['normalizations'] = normalizations

        if registry_reload_error:
            result['registry_reload_error'] = registry_reload_error
            result['message'] = (
                'skill added and skill index updated, but in-memory skill registry reload failed'
            )

        return result

    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}


def finalize_skill_draft(draft_id: str, rebuild_index: bool = True) -> dict[str, Any]:
    try:
        if not isinstance(draft_id, str) or not draft_id.strip():
            return {'status': 'error', 'error': 'draft_id must be a non-empty string'}

        safe_title = safe_skill_title(draft_id)
        if not safe_title:
            return {'status': 'error', 'error': 'draft_id produced an empty safe filename'}

        draft_dir = safe_path('skills/drafts')
        draft_metadata_path = draft_dir / f'{safe_title}.json'
        draft_procedure_path = draft_dir / f'{safe_title}.md'

        if not draft_metadata_path.exists() or not draft_procedure_path.exists():
            return {
                'status': 'error',
                'error': 'skill draft not found',
                'draft_id': safe_title,
                'draft_metadata_path': draft_metadata_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
                'draft_procedure_path': draft_procedure_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
            }

        markdown = draft_procedure_path.read_text(encoding='utf-8')
        try:
            payload = json.loads(draft_metadata_path.read_text(encoding='utf-8'))
        except Exception as exc:
            return {'status': 'error', 'error': f'invalid draft metadata JSON: {exc}', 'draft_id': safe_title}

        if not isinstance(payload, dict):
            return {'status': 'error', 'error': 'draft metadata JSON must be an object', 'draft_id': safe_title}

        field_error = _metadata_field_error(payload, draft_id=safe_title)
        if field_error:
            return field_error

        validation_errors = validate_skill_payload(markdown, payload)
        validation_errors.extend(validate_skill_routing_contract(payload))
        if validation_errors:
            return validation_failure_result(validation_errors, markdown, payload, safe_title)

        return create_skill(safe_title, markdown, payload, rebuild_index=rebuild_index)

    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}


def repair_skill_draft(draft_id: str, repairs: list[dict[str, Any]], normalize: bool = True) -> dict[str, Any]:
    try:
        if not isinstance(draft_id, str) or not draft_id.strip():
            return {'status': 'error', 'error': 'draft_id must be a non-empty string'}
        if not isinstance(repairs, list):
            return {'status': 'error', 'error': 'repairs must be an array'}

        safe_title = safe_skill_title(draft_id)
        if not safe_title:
            return {'status': 'error', 'error': 'draft_id produced an empty safe filename'}

        draft_dir = safe_path('skills/drafts')
        draft_metadata_path = draft_dir / f'{safe_title}.json'
        draft_procedure_path = draft_dir / f'{safe_title}.md'
        if not draft_metadata_path.exists() or not draft_procedure_path.exists():
            return {
                'status': 'error',
                'error': 'skill draft not found',
                'draft_id': safe_title,
            }

        try:
            payload = json.loads(draft_metadata_path.read_text(encoding='utf-8'))
        except Exception as exc:
            return {'status': 'error', 'error': f'invalid draft metadata JSON: {exc}', 'draft_id': safe_title}
        if not isinstance(payload, dict):
            return {'status': 'error', 'error': 'draft metadata JSON must be an object', 'draft_id': safe_title}

        repaired, applied_repairs = apply_structured_repairs(payload, repairs)
        normalizations: list[dict[str, Any]] = []
        if normalize:
            repaired, normalizations = normalize_skill_payload(repaired)

        draft_metadata_path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2), encoding='utf-8')
        markdown = draft_procedure_path.read_text(encoding='utf-8')
        field_error = _metadata_field_error(repaired, draft_id=safe_title)
        if field_error:
            field_error.update({
                'applied_repairs': applied_repairs,
                'normalizations': normalizations,
                'draft_metadata_path': draft_metadata_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
            })
            return field_error

        validation_errors = validate_skill_payload(markdown, repaired)
        validation_errors.extend(validate_skill_routing_contract(repaired))
        if validation_errors:
            result = validation_failure_result(validation_errors, markdown, repaired, safe_title, normalizations)
            result['applied_repairs'] = applied_repairs
            return result

        return {
            'status': 'ok',
            'draft_id': safe_title,
            'draft_metadata_path': draft_metadata_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
            'draft_procedure_path': draft_procedure_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
            'applied_repairs': applied_repairs,
            'normalizations': normalizations,
            'message': 'skill draft repaired; call finalize_skill_draft next',
        }

    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}
