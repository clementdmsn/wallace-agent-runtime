from __future__ import annotations

import sandbox
from tests.conftest import settings_for_sandbox
from tools.review_target_tools import discover_review_targets


def configure_sandbox(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    return settings


def test_discover_review_targets_accepts_single_reviewable_file(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)
    (tmp_path / 'app.py').write_text('print("ok")\n', encoding='utf-8')

    result = discover_review_targets('app.py')

    assert result['status'] == 'ok'
    assert result['count'] == 1
    assert result['targets'][0]['path'] == 'app.py'
    assert result['targets'][0]['suffix'] == '.py'


def test_discover_review_targets_filters_and_limits_project_files(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/app.py').write_text('print("ok")\n', encoding='utf-8')
    (tmp_path / 'src/config.yaml').write_text('debug: true\n', encoding='utf-8')
    (tmp_path / 'src/notes.txt').write_text('ignore\n', encoding='utf-8')
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules/dep.js').write_text('ignore();\n', encoding='utf-8')

    result = discover_review_targets('.', max_files=1)

    assert result['status'] == 'ok'
    assert result['count'] == 1
    assert result['total_candidates'] == 2
    assert result['truncated'] is True
    assert result['targets'][0]['path'] == 'src/app.py'


def test_discover_review_targets_rejects_invalid_limits(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)

    result = discover_review_targets('.', max_files=0)

    assert result['status'] == 'error'
    assert result['error'] == 'max_files must be a positive integer'


def test_discover_review_targets_reports_non_reviewable_file(monkeypatch, tmp_path):
    configure_sandbox(monkeypatch, tmp_path)
    (tmp_path / 'notes.txt').write_text('ignore\n', encoding='utf-8')

    result = discover_review_targets('notes.txt')

    assert result['status'] == 'ok'
    assert result['count'] == 0
    assert result['message'] == 'file extension is not in the review target allowlist'
