import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any

import faiss
import numpy as np

from config import SETTINGS
from sandbox import configured_project_path, configured_sandbox_path, project_relative_path
from tools.embedding import embed_texts


SKILL_INDEX_SCHEMA_VERSION = 2
SKILL_INDEX_CHUNKER_VERSION = 3
_INDEX_WRITE_LOCK = threading.Lock()


def _metadata_source_path(metadata_json_path: str) -> Path:
    return configured_project_path(metadata_json_path)


def _source_rel(source_path: Path) -> str:
    return project_relative_path(source_path)


def _join_lines(label: str, items: list[str]) -> str | None:
    clean = [str(item).strip() for item in items if str(item).strip()]
    if not clean:
        return None
    return f"{label}: " + ' | '.join(clean)


def _base_skill_map() -> dict[str, Any]:
    return {
        'version': SKILL_INDEX_SCHEMA_VERSION,
        'chunker_version': SKILL_INDEX_CHUNKER_VERSION,
        'index_type': 'IndexFlatL2',
        'sources': {},
        'records': [],
    }


def _skill_name(data: Any, source_path: Path) -> str:
    if isinstance(data, dict):
        skill_name = data.get('name')
        if skill_name:
            return str(skill_name).strip() or source_path.stem
    return source_path.stem


# Metadata is chunked into semantic fields so retrieval can match on purpose,
# triggers, inputs, and examples instead of only the skill title.
def _chunk_skill_metadata(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return [str(data)]

    chunks: list[str] = []
    summary = str(data.get('summary', '')).strip()
    description = str(data.get('description', '')).strip()
    categories = [str(item) for item in data.get('categories', []) if str(item).strip()]
    when_to_use = [str(item) for item in data.get('when_to_use', []) if str(item).strip()]
    when_not_to_use = [str(item) for item in data.get('when_not_to_use', []) if str(item).strip()]
    trigger_actions = [str(item) for item in data.get('trigger_actions', []) if str(item).strip()]
    exclusions = [str(item) for item in data.get('exclusions', []) if str(item).strip()]
    examples = [str(item) for item in data.get('examples', []) if str(item).strip()]

    if summary:
        chunks.append(f'summary: {summary}')
    if description:
        chunks.append(f'description: {description}')

    for line in (
        _join_lines('categories', categories),
        _join_lines('when_to_use', when_to_use),
        _join_lines('when_not_to_use', when_not_to_use),
        _join_lines('trigger_actions', trigger_actions),
        _join_lines('exclusions', exclusions),
        _join_lines('examples', examples),
    ):
        if line:
            chunks.append(line)

    inputs = data.get('inputs')
    if isinstance(inputs, dict):
        input_parts = []
        for name, spec in inputs.items():
            if not isinstance(spec, dict):
                continue
            input_type = str(spec.get('type', '')).strip()
            input_desc = str(spec.get('description', '')).strip()
            segment = f'{name} ({input_type})' if input_type else str(name)
            if input_desc:
                segment += f': {input_desc}'
            input_parts.append(segment)
        input_line = _join_lines('inputs', input_parts)
        if input_line:
            chunks.append(input_line)

    return [chunk for chunk in chunks if chunk.strip()]


def _index_file_paths(index_dir: str, index_name: str) -> tuple[Path, Path]:
    root = configured_sandbox_path(index_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f'{index_name}.faiss', root / f'{index_name}.map.json'


def _load_or_create_index(index_path: Path, dim: int) -> faiss.Index:
    if index_path.exists():
        index = faiss.read_index(str(index_path))
        if index.d != dim:
            raise ValueError(f'embedding dimension mismatch: existing={index.d}, new={dim}')
        return index
    return faiss.IndexFlatL2(dim)


def _load_or_create_map(map_path: Path) -> dict[str, Any]:
    if not map_path.exists():
        return _base_skill_map()

    with map_path.open('r', encoding='utf-8') as fh:
        return json.load(fh)


def _atomic_write_index_and_map(index: faiss.Index, index_path: Path, map_path: Path, skill_map: dict[str, Any]) -> None:
    index_tmp = index_path.with_name(f'.{index_path.name}.tmp-{os.getpid()}-{threading.get_ident()}')
    map_tmp = map_path.with_name(f'.{map_path.name}.tmp-{os.getpid()}-{threading.get_ident()}')
    try:
        faiss.write_index(index, str(index_tmp))
        map_tmp.write_text(json.dumps(skill_map, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(index_tmp, index_path)
        os.replace(map_tmp, map_path)
    finally:
        for tmp_path in (index_tmp, map_tmp):
            if tmp_path.exists():
                tmp_path.unlink()


def create_skill_faiss_index(
    metadata_json_path: str,
    index_dir: str = 'skills/indexes',
    index_name: str = 'skills',
) -> dict[str, Any]:
    try:
        source_path = _metadata_source_path(metadata_json_path)
        if source_path.suffix.lower() != '.json':
            return {
                'status': 'error',
                'path': metadata_json_path,
                'error': 'metadata_json_path must point to a .json file',
            }
        if not source_path.exists():
            return {
                'status': 'error',
                'path': metadata_json_path,
                'error': 'metadata file does not exist',
            }

        raw = source_path.read_text(encoding='utf-8')
        data = json.loads(raw)
        chunks = _chunk_skill_metadata(data)
        if not chunks:
            return {
                'status': 'error',
                'path': metadata_json_path,
                'error': 'metadata file produced no embeddable content',
            }

        source_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        source_rel = _source_rel(source_path)

        index_path, map_path = _index_file_paths(index_dir, index_name)
        with _INDEX_WRITE_LOCK:
            skill_map = _load_or_create_map(map_path)
            existing_source = skill_map['sources'].get(source_rel)

            if existing_source:
                if existing_source.get('content_hash') == source_hash:
                    return {
                        'status': 'ok',
                        'path': metadata_json_path,
                        'index_path': index_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
                        'map_path': map_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
                        'created': False,
                        'skipped': True,
                        'message': 'source already indexed and up to date',
                    }
                return {
                    'status': 'error',
                    'path': metadata_json_path,
                    'error': 'source already indexed with different content; run a rebuild flow to refresh the shared index',
                }

        if skill_map.get('chunker_version') not in (None, SKILL_INDEX_CHUNKER_VERSION):
            return {
                'status': 'error',
                'path': metadata_json_path,
                'error': 'existing skill index was built with an older metadata chunker; run rebuild_skill_faiss_index',
                'expected_chunker_version': SKILL_INDEX_CHUNKER_VERSION,
                'actual_chunker_version': skill_map.get('chunker_version'),
            }
        skill_map['version'] = SKILL_INDEX_SCHEMA_VERSION
        skill_map['chunker_version'] = SKILL_INDEX_CHUNKER_VERSION

        vectors = embed_texts(chunks)
        if len(vectors) != len(chunks):
            return {
                'status': 'error',
                'path': metadata_json_path,
                'error': 'embedding backend returned a different number of vectors than chunks',
            }

        matrix = np.asarray(vectors, dtype='float32')
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            return {
                'status': 'error',
                'path': metadata_json_path,
                'error': 'embedding output must be a non-empty 2D array',
            }

        with _INDEX_WRITE_LOCK:
            skill_map = _load_or_create_map(map_path)
            if skill_map.get('chunker_version') not in (None, SKILL_INDEX_CHUNKER_VERSION):
                return {
                    'status': 'error',
                    'path': metadata_json_path,
                    'error': 'existing skill index was built with an older metadata chunker; run rebuild_skill_faiss_index',
                    'expected_chunker_version': SKILL_INDEX_CHUNKER_VERSION,
                    'actual_chunker_version': skill_map.get('chunker_version'),
                }
            existing_source = skill_map['sources'].get(source_rel)
            if existing_source:
                if existing_source.get('content_hash') == source_hash:
                    return {
                        'status': 'ok',
                        'path': metadata_json_path,
                        'index_path': index_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
                        'map_path': map_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
                        'created': False,
                        'skipped': True,
                        'message': 'source already indexed and up to date',
                    }
                return {
                    'status': 'error',
                    'path': metadata_json_path,
                    'error': 'source already indexed with different content; run a rebuild flow to refresh the shared index',
                }

            skill_map['version'] = SKILL_INDEX_SCHEMA_VERSION
            skill_map['chunker_version'] = SKILL_INDEX_CHUNKER_VERSION
            index = _load_or_create_index(index_path, int(matrix.shape[1]))
            start_row = int(index.ntotal)
            index.add(matrix)

            skill_name = _skill_name(data, source_path)

            for i, chunk in enumerate(chunks):
                skill_map['records'].append({
                    'row_id': start_row + i,
                    'source_path': source_rel,
                    'content_hash': source_hash,
                    'skill_name': skill_name,
                    'chunk_index': i,
                    'text': chunk,
                })

            skill_map['sources'][source_rel] = {
                'content_hash': source_hash,
                'skill_name': skill_name,
                'chunk_count': len(chunks),
            }

            _atomic_write_index_and_map(index, index_path, map_path, skill_map)

        return {
            'status': 'ok',
            'path': metadata_json_path,
            'index_path': index_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
            'map_path': map_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
            'created': True,
            'rows_added': len(chunks),
            'total_rows': int(index.ntotal),
            'message': 'skill metadata added to FAISS index',
        }

    except Exception as exc:
        return {'status': 'error', 'path': metadata_json_path, 'error': str(exc)}


def search_skill_faiss_index(
    query: str,
    index_dir: str = 'skills/indexes',
    index_name: str = 'skills',
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
            return {'status': 'error', 'error': 'index does not exist'}

        vectors = embed_texts([query])
        matrix = np.asarray(vectors, dtype='float32')
        if matrix.ndim != 2 or matrix.shape[0] != 1:
            return {'status': 'error', 'error': 'embedding backend must return exactly one query vector'}

        index = faiss.read_index(str(index_path))
        if matrix.shape[1] != index.d:
            return {'status': 'error', 'error': f'query embedding dimension mismatch: index={index.d}, query={matrix.shape[1]}'}

        skill_map = json.loads(map_path.read_text(encoding='utf-8'))
        if skill_map.get('chunker_version') != SKILL_INDEX_CHUNKER_VERSION:
            return {
                'status': 'error',
                'error': (
                    'skill index is stale or was built with an older metadata chunker; '
                    'run rebuild_skill_faiss_index before searching'
                ),
                'expected_chunker_version': SKILL_INDEX_CHUNKER_VERSION,
                'actual_chunker_version': skill_map.get('chunker_version'),
            }
        distances, ids = index.search(matrix, k)
        by_row_id = {int(record['row_id']): record for record in skill_map.get('records', [])}

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
                'skill_name': record['skill_name'],
                'source_path': record['source_path'],
                'chunk_index': record['chunk_index'],
                'text': record['text'],
            })

        return {'status': 'ok', 'query': query, 'count': len(matches), 'matches': matches}

    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}


def rebuild_skill_faiss_index(
    metadata_json_paths: list[str],
    index_dir: str = 'skills/indexes',
    index_name: str = 'skills',
) -> dict[str, Any]:
    try:
        if not isinstance(metadata_json_paths, list) or not metadata_json_paths:
            return {'status': 'error', 'error': 'metadata_json_paths must be a non-empty list of paths'}

        all_rows: list[dict[str, Any]] = []
        all_vectors: list[list[float]] = []
        sources: dict[str, Any] = {}
        index_path, map_path = _index_file_paths(index_dir, index_name)

        for metadata_json_path in metadata_json_paths:
            source_path = _metadata_source_path(metadata_json_path)
            if source_path.suffix.lower() != '.json':
                return {'status': 'error', 'path': metadata_json_path, 'error': 'metadata_json_path must point to a .json file'}
            if not source_path.exists():
                return {'status': 'error', 'path': metadata_json_path, 'error': 'metadata file does not exist'}

            raw = source_path.read_text(encoding='utf-8')
            data = json.loads(raw)
            chunks = _chunk_skill_metadata(data)
            if not chunks:
                continue

            vectors = embed_texts(chunks)
            if len(vectors) != len(chunks):
                return {'status': 'error', 'path': metadata_json_path, 'error': 'embedding backend returned a different number of vectors than chunks'}

            source_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
            source_rel = _source_rel(source_path)
            skill_name = _skill_name(data, source_path)

            start_row = len(all_rows)
            for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=False)):
                all_rows.append({
                    'row_id': start_row + i,
                    'source_path': source_rel,
                    'content_hash': source_hash,
                    'skill_name': skill_name,
                    'chunk_index': i,
                    'text': chunk,
                })
                all_vectors.append(vector)

            sources[source_rel] = {
                'content_hash': source_hash,
                'skill_name': skill_name,
                'chunk_count': len(chunks),
            }

        if not all_vectors:
            return {'status': 'error', 'error': 'no embeddable content found'}

        matrix = np.asarray(all_vectors, dtype='float32')
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            return {'status': 'error', 'error': 'embedding output must be a non-empty 2D array'}

        index = faiss.IndexFlatL2(int(matrix.shape[1]))
        index.add(matrix)

        skill_map = _base_skill_map()
        skill_map['sources'] = sources
        skill_map['records'] = all_rows
        with _INDEX_WRITE_LOCK:
            _atomic_write_index_and_map(index, index_path, map_path, skill_map)

        return {
            'status': 'ok',
            'index_path': index_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
            'map_path': map_path.relative_to(SETTINGS.sandbox_dir).as_posix(),
            'source_count': len(sources),
            'total_rows': int(index.ntotal),
            'message': 'skill FAISS index rebuilt',
        }

    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}
