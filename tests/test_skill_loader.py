from __future__ import annotations

import logging

import sandbox
import skills.loader as skill_loader
from tests.conftest import settings_for_sandbox


def test_load_skill_from_metadata_logs_invalid_json(monkeypatch, tmp_path, caplog):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_loader, 'SETTINGS', settings)

    metadata_path = tmp_path / 'skills' / 'metadatas' / 'broken.json'
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text('{broken json', encoding='utf-8')

    with caplog.at_level(logging.WARNING, logger='skills.loader'):
        result = skill_loader.load_skill_from_metadata(metadata_path)

    assert result is None
    assert 'failed to load skill metadata' in caplog.text


def test_load_skill_from_metadata_logs_non_object(monkeypatch, tmp_path, caplog):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(skill_loader, 'SETTINGS', settings)

    metadata_path = tmp_path / 'skills' / 'metadatas' / 'array.json'
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text('[]', encoding='utf-8')

    with caplog.at_level(logging.WARNING, logger='skills.loader'):
        result = skill_loader.load_skill_from_metadata(metadata_path)

    assert result is None
    assert 'is not a JSON object' in caplog.text
