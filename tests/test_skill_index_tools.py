from __future__ import annotations

import json

import sandbox
import tools.skill_index_tools as skill_index_tools
from tests.conftest import settings_for_sandbox
from tools.skill_index_tools import create_skill_faiss_index, rebuild_skill_faiss_index, search_skill_faiss_index


def _write_metadata(path, name: str | None = 'demo_skill') -> None:
    payload = {
        'summary': 'Demo summary',
        'description': 'Demo description',
        'categories': ['demo'],
        'when_to_use': ['Use for demos'],
        'trigger_actions': ['demo'],
    }
    if name is not None:
        payload['name'] = name
    path.write_text(json.dumps(payload), encoding='utf-8')


def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
    return [[float(index), float(index + 1)] for index, _ in enumerate(texts)]


def test_create_skill_index_uses_source_stem_when_metadata_name_is_blank(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'embed_texts', _fake_embed_texts)

    metadata_path = tmp_path / 'skill_catalog' / 'metadatas' / 'stem_skill.json'
    metadata_path.parent.mkdir(parents=True)
    _write_metadata(metadata_path, name='  ')

    result = create_skill_faiss_index('skill_catalog/metadatas/stem_skill.json')

    assert result['status'] == 'ok'
    map_data = json.loads((tmp_path / result['map_path']).read_text(encoding='utf-8'))
    assert map_data['sources']['skill_catalog/metadatas/stem_skill.json']['skill_name'] == 'stem_skill'


def test_rebuild_skill_index_writes_base_map_shape(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'embed_texts', _fake_embed_texts)

    metadata_path = tmp_path / 'skill_catalog' / 'metadatas' / 'demo.json'
    metadata_path.parent.mkdir(parents=True)
    _write_metadata(metadata_path)

    result = rebuild_skill_faiss_index(['skill_catalog/metadatas/demo.json'])

    assert result['status'] == 'ok'
    map_data = json.loads((tmp_path / result['map_path']).read_text(encoding='utf-8'))
    assert map_data['version'] == skill_index_tools.SKILL_INDEX_SCHEMA_VERSION
    assert map_data['chunker_version'] == skill_index_tools.SKILL_INDEX_CHUNKER_VERSION
    assert map_data['index_type'] == 'IndexFlatL2'
    assert map_data['sources']['skill_catalog/metadatas/demo.json']['skill_name'] == 'demo_skill'
    assert map_data['records']


def test_search_skill_index_returns_matches(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'embed_texts', lambda texts: [[0.0, 1.0] for _ in texts])

    metadata_path = tmp_path / 'skill_catalog' / 'metadatas' / 'demo.json'
    metadata_path.parent.mkdir(parents=True)
    _write_metadata(metadata_path)
    rebuild = rebuild_skill_faiss_index(['skill_catalog/metadatas/demo.json'])
    assert rebuild['status'] == 'ok'

    result = search_skill_faiss_index('demo', k=1)

    assert result['status'] == 'ok'
    assert result['count'] == 1
    assert result['matches'][0]['skill_name'] == 'demo_skill'


def test_search_skill_index_rejects_bad_inputs(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'SETTINGS', settings)

    assert search_skill_faiss_index(123)['error'] == 'query must be a string'
    assert search_skill_faiss_index('   ')['error'] == 'empty query'
    assert search_skill_faiss_index('demo', k=0)['error'] == 'k must be a positive integer'
    assert search_skill_faiss_index('demo')['error'] == 'index does not exist'


def test_create_skill_index_rejects_duplicate_changed_source(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'embed_texts', _fake_embed_texts)

    metadata_path = tmp_path / 'skill_catalog' / 'metadatas' / 'demo.json'
    metadata_path.parent.mkdir(parents=True)
    _write_metadata(metadata_path)

    first = create_skill_faiss_index('skill_catalog/metadatas/demo.json')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    metadata['summary'] = 'Changed summary'
    metadata_path.write_text(json.dumps(metadata), encoding='utf-8')
    second = create_skill_faiss_index('skill_catalog/metadatas/demo.json')

    assert first['status'] == 'ok'
    assert second['status'] == 'error'
    assert 'run a rebuild flow' in second['error']


def test_rebuild_skill_index_reports_no_embeddable_content(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'SETTINGS', settings)

    metadata_path = tmp_path / 'skill_catalog' / 'metadatas' / 'empty.json'
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text('{}', encoding='utf-8')

    result = rebuild_skill_faiss_index(['skill_catalog/metadatas/empty.json'])

    assert result['status'] == 'error'
    assert result['error'] == 'no embeddable content found'


def test_create_skill_index_rejects_bad_paths_and_empty_metadata(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'SETTINGS', settings)

    text_path = tmp_path / 'skill_catalog' / 'metadatas' / 'demo.txt'
    text_path.parent.mkdir(parents=True)
    text_path.write_text('not json', encoding='utf-8')

    assert create_skill_faiss_index('skill_catalog/metadatas/demo.txt')['error'] == 'metadata_json_path must point to a .json file'
    assert create_skill_faiss_index('skill_catalog/metadatas/missing.json')['error'] == 'metadata file does not exist'

    empty_path = tmp_path / 'skill_catalog' / 'metadatas' / 'empty.json'
    empty_path.write_text('{}', encoding='utf-8')
    assert create_skill_faiss_index('skill_catalog/metadatas/empty.json')['error'] == 'metadata file produced no embeddable content'


def test_create_skill_index_reports_embedding_shape_errors(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'SETTINGS', settings)

    metadata_path = tmp_path / 'skill_catalog' / 'metadatas' / 'demo.json'
    metadata_path.parent.mkdir(parents=True)
    _write_metadata(metadata_path)

    monkeypatch.setattr(skill_index_tools, 'embed_texts', lambda texts: [])
    wrong_count = create_skill_faiss_index('skill_catalog/metadatas/demo.json')
    assert wrong_count['error'] == 'embedding backend returned a different number of vectors than chunks'

    monkeypatch.setattr(skill_index_tools, 'embed_texts', lambda texts: [1.0 for _ in texts])
    bad_shape = create_skill_faiss_index('skill_catalog/metadatas/demo.json')
    assert bad_shape['error'] == 'embedding output must be a non-empty 2D array'


def test_create_skill_index_reports_stale_chunker_version(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'SETTINGS', settings)

    metadata_path = tmp_path / 'skill_catalog' / 'metadatas' / 'demo.json'
    metadata_path.parent.mkdir(parents=True)
    _write_metadata(metadata_path)

    index_dir = tmp_path / 'skills' / 'indexes'
    index_dir.mkdir(parents=True)
    (index_dir / 'skills.map.json').write_text(
        json.dumps({**skill_index_tools._base_skill_map(), 'chunker_version': 1}),
        encoding='utf-8',
    )

    result = create_skill_faiss_index('skill_catalog/metadatas/demo.json')

    assert result['status'] == 'error'
    assert 'older metadata chunker' in result['error']


def test_search_skill_index_reports_embedding_and_stale_map_errors(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'embed_texts', lambda texts: [[0.0, 1.0] for _ in texts])

    metadata_path = tmp_path / 'skill_catalog' / 'metadatas' / 'demo.json'
    metadata_path.parent.mkdir(parents=True)
    _write_metadata(metadata_path)
    assert rebuild_skill_faiss_index(['skill_catalog/metadatas/demo.json'])['status'] == 'ok'

    monkeypatch.setattr(skill_index_tools, 'embed_texts', lambda texts: [])
    bad_query_shape = search_skill_faiss_index('demo')
    assert bad_query_shape['error'] == 'embedding backend must return exactly one query vector'

    monkeypatch.setattr(skill_index_tools, 'embed_texts', lambda texts: [[0.0, 1.0, 2.0]])
    mismatch = search_skill_faiss_index('demo')
    assert mismatch['error'] == 'query embedding dimension mismatch: index=2, query=3'

    map_path = tmp_path / 'skills' / 'indexes' / 'skills.map.json'
    stale_map = json.loads(map_path.read_text(encoding='utf-8'))
    stale_map['chunker_version'] = 1
    map_path.write_text(json.dumps(stale_map), encoding='utf-8')
    monkeypatch.setattr(skill_index_tools, 'embed_texts', lambda texts: [[0.0, 1.0]])
    stale = search_skill_faiss_index('demo')
    assert stale['status'] == 'error'
    assert 'skill index is stale' in stale['error']


def test_rebuild_skill_index_rejects_bad_inputs_and_embedding_count(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_index_tools, 'SETTINGS', settings)

    assert rebuild_skill_faiss_index([])['error'] == 'metadata_json_paths must be a non-empty list of paths'

    text_path = tmp_path / 'skill_catalog' / 'metadatas' / 'demo.txt'
    text_path.parent.mkdir(parents=True)
    text_path.write_text('not json', encoding='utf-8')
    assert rebuild_skill_faiss_index(['skill_catalog/metadatas/demo.txt'])['error'] == 'metadata_json_path must point to a .json file'
    assert rebuild_skill_faiss_index(['skill_catalog/metadatas/missing.json'])['error'] == 'metadata file does not exist'

    metadata_path = tmp_path / 'skill_catalog' / 'metadatas' / 'demo.json'
    _write_metadata(metadata_path)
    monkeypatch.setattr(skill_index_tools, 'embed_texts', lambda texts: [])
    result = rebuild_skill_faiss_index(['skill_catalog/metadatas/demo.json'])
    assert result['error'] == 'embedding backend returned a different number of vectors than chunks'
