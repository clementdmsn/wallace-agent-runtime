from __future__ import annotations

import json

import sandbox
from tests.conftest import settings_for_sandbox
from tools import owasp_reference_tools


def configure_sandbox(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(owasp_reference_tools, 'SETTINGS', settings)
    return settings


def fake_embed_texts(texts: list[str]) -> list[list[float]]:
    vectors = []
    for text in texts:
        lowered = text.lower()
        vectors.append([
            float('injection' in lowered or 'query' in lowered),
            float('log' in lowered),
            float(len(text) % 17) / 17.0,
        ])
    return vectors


def valid_record(reference_id: str = 'v5.0.0-V1.2.4') -> dict[str, str]:
    return {
        'source': 'ASVS',
        'version': '5.0.0',
        'reference_id': reference_id,
        'title': 'Injection Prevention',
        'category': 'Encoding and Sanitization',
        'url': 'https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release',
        'text': 'Verify that database queries use parameterized queries to prevent injection.',
    }


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        ''.join(json.dumps(record) + '\n' for record in records),
        encoding='utf-8',
    )


def test_validate_owasp_corpus_accepts_valid_records(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)
    write_jsonl(tmp_path / 'knowledge_base/owasp/corpus.jsonl', [valid_record()])

    result = owasp_reference_tools.validate_owasp_corpus()

    assert result['status'] == 'ok'
    assert result['record_count'] == 1
    assert result['errors'] == []


def test_validate_owasp_corpus_reports_missing_and_duplicate_records(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)
    duplicate = valid_record()
    missing = dict(valid_record('v5.0.0-V1.2.5'))
    del missing['text']
    write_jsonl(tmp_path / 'knowledge_base/owasp/corpus.jsonl', [duplicate, duplicate, missing])

    result = owasp_reference_tools.validate_owasp_corpus()

    assert result['status'] == 'error'
    assert result['record_count'] == 1
    errors = [item['error'] for item in result['errors']]
    assert 'duplicate reference id: v5.0.0-V1.2.4' in errors
    assert 'missing required field(s): text' in errors


def test_rebuild_and_search_owasp_reference_index(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(owasp_reference_tools, 'embed_texts', fake_embed_texts)
    write_jsonl(
        tmp_path / 'knowledge_base/owasp/corpus.jsonl',
        [
            valid_record('v5.0.0-V1.2.4'),
            {
                **valid_record('v5.0.0-V16.2.5'),
                'title': 'Sensitive Logging',
                'category': 'Security Logging and Error Handling',
                'text': 'Verify that sensitive data is masked or omitted from application logs.',
            },
        ],
    )

    rebuild = owasp_reference_tools.rebuild_owasp_reference_index()
    search = owasp_reference_tools.search_owasp_reference('sql injection query', k=1)

    assert rebuild['status'] == 'ok'
    assert rebuild['record_count'] == 2
    assert search['status'] == 'ok'
    assert search['count'] == 1
    assert search['matches'][0]['reference_id'] == 'v5.0.0-V1.2.4'
    assert search['matches'][0]['url'].startswith('https://')


def test_search_owasp_reference_reports_missing_index(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)

    result = owasp_reference_tools.search_owasp_reference('injection')

    assert result['status'] == 'error'
    assert result['error'] == 'OWASP reference index does not exist'
