from __future__ import annotations

import importlib
import sys

import pytest


def reload_config(monkeypatch):
    sys.modules.pop('config', None)
    return importlib.import_module('config')


def test_config_defaults_to_local_provider(monkeypatch):
    monkeypatch.delenv('WALLACE_MODEL_PROVIDER', raising=False)
    monkeypatch.delenv('WALLACE_MODEL', raising=False)
    monkeypatch.delenv('WALLACE_BASE_URL', raising=False)
    monkeypatch.delenv('WALLACE_API_KEY', raising=False)
    monkeypatch.delenv('WALLACE_HOST', raising=False)
    monkeypatch.delenv('WALLACE_PORT', raising=False)

    config = reload_config(monkeypatch)

    assert config.SETTINGS.model_provider == 'local'
    assert config.SETTINGS.model_name == 'unsloth/qwen3-4b-instruct-2507'
    assert config.SETTINGS.base_url == 'http://localhost:1234/v1'
    assert config.SETTINGS.api_key == 'lmstudio'
    assert config.SETTINGS.host == '127.0.0.1'
    assert config.SETTINGS.port == 8000
    assert config.SETTINGS.project_dir.as_posix() == '/opt/wallace'
    assert config.SETTINGS.skill_metadata_dir == 'skill_catalog/metadatas'
    assert config.SETTINGS.skill_procedure_dir == 'skill_catalog/procedures'
    assert config.SETTINGS.skill_index_dir == 'skills/indexes'
    assert config.SETTINGS.run_trace_payloads is False


def test_explicit_backend_env_overrides_provider_defaults(monkeypatch):
    monkeypatch.setenv('WALLACE_MODEL_PROVIDER', 'local')
    monkeypatch.setenv('WALLACE_MODEL', 'custom-model')
    monkeypatch.setenv('WALLACE_BASE_URL', 'http://example.test/v1')
    monkeypatch.setenv('WALLACE_API_KEY', 'env-key')

    config = reload_config(monkeypatch)

    assert config.SETTINGS.model_name == 'custom-model'
    assert config.SETTINGS.base_url == 'http://example.test/v1'
    assert config.SETTINGS.api_key == 'env-key'


def test_config_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv('WALLACE_MODEL_PROVIDER', 'unknown')

    with pytest.raises(ValueError, match='WALLACE_MODEL_PROVIDER'):
        reload_config(monkeypatch)


def test_config_rejects_invalid_integer_env(monkeypatch):
    monkeypatch.setenv('WALLACE_MAX_AUTO_TURNS', 'many')

    with pytest.raises(ValueError, match='WALLACE_MAX_AUTO_TURNS'):
        reload_config(monkeypatch)


def test_build_settings_accepts_explicit_env_without_mutating_process(monkeypatch):
    monkeypatch.delenv('WALLACE_MODEL_PROVIDER', raising=False)
    config = reload_config(monkeypatch)

    settings = config.build_settings({
        'WALLACE_MODEL_PROVIDER': 'local',
        'WALLACE_MODEL': 'explicit-model',
        'WALLACE_MAX_TOOL_OUTPUT': '123',
        'WALLACE_CURL_WHITELIST_PATH': '/tmp/wallace-curl.json',
        'WALLACE_HOST': '0.0.0.0',
        'WALLACE_PORT': '8080',
    })

    assert settings.model_name == 'explicit-model'
    assert settings.max_tool_output == 123
    assert str(settings.curl_whitelist_path) == '/tmp/wallace-curl.json'
    assert settings.host == '0.0.0.0'
    assert settings.port == 8080
    assert config.SETTINGS.model_name == 'unsloth/qwen3-4b-instruct-2507'


def test_blank_model_env_uses_default_model(monkeypatch):
    monkeypatch.delenv('WALLACE_MODEL_PROVIDER', raising=False)
    config = reload_config(monkeypatch)

    settings = config.build_settings({
        'WALLACE_MODEL': '',
        'WALLACE_EMBEDDING_MODEL': '',
    })

    assert settings.model_name == 'unsloth/qwen3-4b-instruct-2507'
    assert settings.embedding_model_name == 'unsloth/qwen3-4b-instruct-2507'
