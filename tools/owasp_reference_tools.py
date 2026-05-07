from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any

import faiss
import numpy as np

from config import SETTINGS
from sandbox import configured_sandbox_path
from tools.embedding import embed_texts


OWASP_INDEX_SCHEMA_VERSION = 1
OWASP_INDEX_CHUNKER_VERSION = 1
OWASP_DEFAULT_CORPUS_PATH = 'knowledge_base/owasp/corpus.jsonl'
OWASP_DEFAULT_INDEX_DIR = 'knowledge_base/owasp/indexes'
OWASP_DEFAULT_INDEX_NAME = 'owasp'

REQUIRED_OWASP_RECORD_FIELDS = {
    'source',
    'version',
    'reference_id',
    'title',
    'category',
    'url',
    'text',
}
SUPPORTED_OWASP_SOURCES = {'ASVS', 'Top10'}
SUPPORTED_OWASP_VERSIONS = {'5.0.0', '2025'}

_INDEX_WRITE_LOCK = threading.Lock()


def _base_reference_map() -> dict[str, Any]:
    return {
        'version': OWASP_INDEX_SCHEMA_VERSION,
        'chunker_version': OWASP_INDEX_CHUNKER_VERSION,
        'index_type': 'IndexFlatL2',
        'corpus_path': None,
        'corpus_hash': None,
        'records': [],
    }


def _index_file_paths(index_dir: str, index_name: str) -> tuple[Path, Path]:
    root = configured_sandbox_path(index_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f'{index_name}.faiss', root / f'{index_name}.map.json'


def _atomic_write_index_and_map(index: faiss.Index, index_path: Path, map_path: Path, reference_map: dict[str, Any]) -> None:
    index_tmp = index_path.with_name(f'.{index_path.name}.tmp-{os.getpid()}-{threading.get_ident()}')
    map_tmp = map_path.with_name(f'.{map_path.name}.tmp-{os.getpid()}-{threading.get_ident()}')
    try:
        faiss.write_index(index, str(index_tmp))
        map_tmp.write_text(json.dumps(reference_map, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(index_tmp, index_path)
        os.replace(map_tmp, map_path)
    finally:
        for tmp_path in (index_tmp, map_tmp):
            if tmp_path.exists():
                tmp_path.unlink()


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    return ' '.join(value.strip().split())


def validate_owasp_reference_record(record: Any) -> tuple[dict[str, str] | None, str | None]:
    if not isinstance(record, dict):
        return None, 'record must be a JSON object'

    missing = sorted(REQUIRED_OWASP_RECORD_FIELDS - set(record))
    if missing:
        return None, f'missing required field(s): {", ".join(missing)}'

    normalized: dict[str, str] = {}
    for field in sorted(REQUIRED_OWASP_RECORD_FIELDS):
        value = _clean_text(record.get(field))
        if not value:
            return None, f'field {field} must be a non-empty string'
        normalized[field] = value

    if normalized['source'] not in SUPPORTED_OWASP_SOURCES:
        return None, f'unsupported source: {normalized["source"]}'
    if normalized['version'] not in SUPPORTED_OWASP_VERSIONS:
        return None, f'unsupported version: {normalized["version"]}'
    if not normalized['url'].startswith('https://'):
        return None, 'url must be HTTPS'

    return normalized, None


def load_owasp_corpus(corpus_path: str = OWASP_DEFAULT_CORPUS_PATH) -> tuple[list[dict[str, str]], list[dict[str, Any]], str]:
    path = configured_sandbox_path(corpus_path)
    if not path.exists():
        raise FileNotFoundError('OWASP corpus does not exist')
    if path.is_dir():
        raise ValueError('OWASP corpus path is a directory')

    raw = path.read_text(encoding='utf-8')
    records: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []
    seen_ids: set[tuple[str, str, str]] = set()

    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append({'line': line_number, 'error': f'invalid JSON: {exc.msg}'})
            continue

        record, error = validate_owasp_reference_record(payload)
        if error or record is None:
            errors.append({'line': line_number, 'error': error})
            continue

        identity = (record['source'], record['version'], record['reference_id'])
        if identity in seen_ids:
            errors.append({'line': line_number, 'error': f'duplicate reference id: {record["reference_id"]}'})
            continue
        seen_ids.add(identity)
        records.append(record)

    return records, errors, raw


def validate_owasp_corpus(corpus_path: str = OWASP_DEFAULT_CORPUS_PATH) -> dict[str, Any]:
    try:
        records, errors, raw = load_owasp_corpus(corpus_path)
        return {
            'status': 'ok' if not errors else 'error',
            'path': corpus_path,
            'record_count': len(records),
            'errors': errors,
            'content_hash': hashlib.sha256(raw.encode('utf-8')).hexdigest(),
        }
    except Exception as exc:
        return {'status': 'error', 'path': corpus_path, 'error': str(exc)}


def _record_embedding_text(record: dict[str, str]) -> str:
    return (
        f'source: {record["source"]} {record["version"]}\n'
        f'reference: {record["reference_id"]}\n'
        f'title: {record["title"]}\n'
        f'category: {record["category"]}\n'
        f'text: {record["text"]}'
    )


def rebuild_owasp_reference_index(
    corpus_path: str = OWASP_DEFAULT_CORPUS_PATH,
    index_dir: str = OWASP_DEFAULT_INDEX_DIR,
    index_name: str = OWASP_DEFAULT_INDEX_NAME,
) -> dict[str, Any]:
    try:
        records, errors, raw = load_owasp_corpus(corpus_path)
        if errors:
            return {'status': 'error', 'path': corpus_path, 'errors': errors}
        if not records:
            return {'status': 'error', 'path': corpus_path, 'error': 'no valid OWASP corpus records found'}

        chunks = [_record_embedding_text(record) for record in records]
        vectors = embed_texts(chunks)
        if len(vectors) != len(chunks):
            return {'status': 'error', 'error': 'embedding backend returned a different number of vectors than records'}

        matrix = np.asarray(vectors, dtype='float32')
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            return {'status': 'error', 'error': 'embedding output must be a non-empty 2D array'}

        index = faiss.IndexFlatL2(int(matrix.shape[1]))
        index.add(matrix)

        sandbox_root = SETTINGS.sandbox_dir.resolve()
        corpus_full_path = configured_sandbox_path(corpus_path)
        reference_map = _base_reference_map()
        reference_map['corpus_path'] = corpus_full_path.relative_to(sandbox_root).as_posix()
        reference_map['corpus_hash'] = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        reference_map['records'] = [
            {
                'row_id': row_id,
                **record,
            }
            for row_id, record in enumerate(records)
        ]

        index_path, map_path = _index_file_paths(index_dir, index_name)
        with _INDEX_WRITE_LOCK:
            _atomic_write_index_and_map(index, index_path, map_path, reference_map)

        return {
            'status': 'ok',
            'index_path': index_path.relative_to(sandbox_root).as_posix(),
            'map_path': map_path.relative_to(sandbox_root).as_posix(),
            'record_count': len(records),
            'total_rows': int(index.ntotal),
            'message': 'OWASP reference index rebuilt',
        }
    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}


def search_owasp_reference(
    query: str,
    index_dir: str = OWASP_DEFAULT_INDEX_DIR,
    index_name: str = OWASP_DEFAULT_INDEX_NAME,
    k: int = 5,
) -> dict[str, Any]:
    try:
        if not isinstance(query, str):
            return {'status': 'error', 'error': 'query must be a string'}
        query = query.strip()
        if not query:
            return {'status': 'error', 'error': 'empty query'}
        if not isinstance(k, int) or k <= 0:
            return {'status': 'error', 'error': 'k must be a positive integer'}

        index_path, map_path = _index_file_paths(index_dir, index_name)
        if not index_path.exists() or not map_path.exists():
            return {'status': 'error', 'error': 'OWASP reference index does not exist'}

        vectors = embed_texts([query])
        matrix = np.asarray(vectors, dtype='float32')
        if matrix.ndim != 2 or matrix.shape[0] != 1:
            return {'status': 'error', 'error': 'embedding backend must return exactly one query vector'}

        index = faiss.read_index(str(index_path))
        if matrix.shape[1] != index.d:
            return {'status': 'error', 'error': f'query embedding dimension mismatch: index={index.d}, query={matrix.shape[1]}'}

        reference_map = json.loads(map_path.read_text(encoding='utf-8'))
        if reference_map.get('chunker_version') != OWASP_INDEX_CHUNKER_VERSION:
            return {
                'status': 'error',
                'error': 'OWASP reference index is stale; run rebuild_owasp_reference_index before searching',
                'expected_chunker_version': OWASP_INDEX_CHUNKER_VERSION,
                'actual_chunker_version': reference_map.get('chunker_version'),
            }

        by_row_id = {int(record['row_id']): record for record in reference_map.get('records', [])}
        distances, ids = index.search(matrix, k)
        matches: list[dict[str, Any]] = []
        for row_id, distance in zip(ids[0], distances[0], strict=False):
            if row_id < 0:
                continue
            record = by_row_id.get(int(row_id))
            if not record:
                continue
            matches.append({
                'row_id': int(row_id),
                'distance': float(distance),
                'source': record['source'],
                'version': record['version'],
                'reference_id': record['reference_id'],
                'title': record['title'],
                'category': record['category'],
                'url': record['url'],
                'text': record['text'],
            })

        return {'status': 'ok', 'query': query, 'count': len(matches), 'matches': matches}
    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}
