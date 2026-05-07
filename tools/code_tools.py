from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sandbox import safe_path
from utils.code_to_sym import extract_symbols_from_file
from utils.sym_to_md import render_markdown


# Code tools expose deterministic source inspection to the model. They should
# prefer parsed symbols over raw file reading when answering code questions.
def summarize_code_file(path: str) -> dict[str, Any]:
    try:
        full = safe_path(path)
        if not full.exists():
            return {'status': 'error', 'path': path, 'error': 'file does not exist'}
        if full.is_dir():
            return {'status': 'error', 'path': path, 'error': 'path is a directory'}

        sym = extract_symbols_from_file(str(full), mode='summary')
        content = render_markdown(sym)
        return {'status': 'ok', 'path': path, 'content': content}

    except Exception as exc:
        return {
            'status': 'error',
            'path': path,
            'error': str(exc),
            'content': f'cwd: {os.getcwd()}, path: {path}, resolved_path: {Path(path).resolve()}',
        }


def list_code_symbols(path: str) -> dict[str, Any]:
    try:
        full = safe_path(path)
        if not full.exists():
            return {'status': 'error', 'path': path, 'error': 'file does not exist'}
        if full.is_dir():
            return {'status': 'error', 'path': path, 'error': 'path is a directory'}

        doc = extract_symbols_from_file(str(full), mode='index')
        symbols: list[dict[str, Any]] = []
        for sym in doc.get('symbols', []):
            symbols.append({
                'name': sym.get('name'),
                'qualified_name': sym.get('qualified_name'),
                'kind': sym.get('kind'),
                'lines': [sym.get('lineno'), sym.get('end_lineno')],
            })

        return {'status': 'ok', 'path': path, 'symbols': symbols, 'content': symbols}
    except SyntaxError as exc:
        return {'status': 'error', 'path': path, 'error': f'python syntax error at line {exc.lineno}: {exc.msg}'}
    except Exception as exc:
        return {'status': 'error', 'path': path, 'error': str(exc)}


def _stringify_items(items: list[Any], key_candidates: tuple[str, ...] = ('name', 'expr', 'target')) -> list[str]:
    out: list[str] = []

    for item in items:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            value = None
            for key in key_candidates:
                if key in item and item[key]:
                    value = item[key]
                    break
            out.append(str(value) if value is not None else str(item))
        else:
            out.append(str(item))

    return out


def explain_function_for_model(path: str, symbol: str) -> dict[str, Any]:
    try:
        full = safe_path(path)
        if not full.exists():
            return {'status': 'error', 'path': path, 'symbol': symbol, 'error': 'file does not exist'}
        if full.is_dir():
            return {'status': 'error', 'path': path, 'symbol': symbol, 'error': 'path is a directory'}

        doc = extract_symbols_from_file(str(full), mode='summary')
        symbols = doc.get('symbols', [])

        exact_matches = []
        name_matches = []

        for sym in symbols:
            qname = sym.get('qualified_name') or sym.get('name')
            name = sym.get('name')

            if qname == symbol:
                exact_matches.append(sym)
            elif name == symbol:
                name_matches.append(sym)

        if exact_matches:
            target = exact_matches[0]
        elif len(name_matches) == 1:
            target = name_matches[0]
        elif len(name_matches) > 1:
            return {
                'status': 'error',
                'path': path,
                'symbol': symbol,
                'error': 'symbol is ambiguous',
                'content': [m.get('qualified_name') or m.get('name') for m in name_matches],
            }
        else:
            return {
                'status': 'error',
                'path': path,
                'symbol': symbol,
                'error': 'symbol not found',
            }

        calls = _stringify_items(target.get('calls', []), ('name', 'expr', 'target'))
        returns = _stringify_items(target.get('returns', []), ('expr', 'name', 'target'))
        raises_ = _stringify_items(target.get('raises', []), ('expr', 'name', 'target'))
        writes = _stringify_items(target.get('writes', []), ('target', 'name', 'expr'))
        reads = _stringify_items(target.get('reads', []), ('name', 'target', 'expr'))
        params = target.get('params', [])
        decorators = target.get('decorators', [])
        instance_attributes = target.get('instance_attributes', [])
        nested_symbols = [
            n.get('qualified_name') or n.get('name')
            for n in target.get('nested_symbols', [])
        ]

        effects: list[str] = []
        if writes or instance_attributes:
            effects.append('state_mutation')
        if any('.' in c for c in calls):
            effects.append('external_or_object_interaction')
        if raises_:
            effects.append('exception_path')

        summary_parts: list[str] = []
        if calls:
            summary_parts.append(f"calls {', '.join(calls[:5])}")
        if writes:
            summary_parts.append(f"writes {', '.join(writes[:5])}")
        if returns:
            summary_parts.append(f"returns {', '.join(returns[:3])}")
        if not summary_parts:
            summary_parts.append('has no obvious side effects or calls')

        return {
            'status': 'ok',
            'path': path,
            'symbol': symbol,
            'content': {
                'qualified_name': target.get('qualified_name') or target.get('name'),
                'kind': target.get('kind'),
                'lines': [target.get('lineno'), target.get('end_lineno')],
                'docstring': target.get('docstring'),
                'params': params,
                'decorators': decorators,
                'calls': calls,
                'returns': returns,
                'raises': raises_,
                'writes': writes,
                'reads': reads,
                'instance_attributes': instance_attributes,
                'nested_symbols': nested_symbols,
                'effects': effects,
                'summary': '; '.join(summary_parts),
            },
        }

    except SyntaxError as exc:
        return {
            'status': 'error',
            'path': path,
            'symbol': symbol,
            'error': f'python syntax error at line {exc.lineno}: {exc.msg}',
        }
    except Exception as exc:
        return {
            'status': 'error',
            'path': path,
            'symbol': symbol,
            'error': str(exc),
            'error_type': type(exc).__name__,
            'repr': repr(exc),
        }
