from dataclasses import dataclass
from pathlib import Path
import os
from typing import Mapping

VALID_MODEL_PROVIDERS = {'local'}


def env_text(name: str, default: str, env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    value = env.get(name)
    if value is None or not value.strip():
        return default
    return value


def env_bool(name: str, default: bool, env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    value = env.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def configured_provider(env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    provider = env.get('WALLACE_MODEL_PROVIDER', 'local').strip().lower()
    if provider not in VALID_MODEL_PROVIDERS:
        allowed = ', '.join(sorted(VALID_MODEL_PROVIDERS))
        raise ValueError(f'WALLACE_MODEL_PROVIDER must be one of: {allowed}')
    return provider


def env_int(name: str, default: int, *, minimum: int = 1, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f'{name} must be an integer') from exc
    if value < minimum:
        raise ValueError(f'{name} must be >= {minimum}')
    return value


def chat_base_url(provider: str, env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return env_text('WALLACE_BASE_URL', 'http://localhost:1234/v1', env)


def chat_api_key(provider: str, env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return env_text('WALLACE_API_KEY', 'lmstudio', env)


def chat_model_name(provider: str, env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return env_text('WALLACE_MODEL', 'unsloth/qwen3-4b-instruct-2507', env)


@dataclass(frozen=True)
class Settings:
    project_dir: Path = Path('/opt/wallace')
    host: str = '127.0.0.1'
    port: int = 8000
    sandbox_dir: Path = Path('/opt/wallace/sandbox')
    curl_whitelist_path: Path = Path('/var/lib/wallace/curl_whitelist.json')
    model_provider: str = 'local'
    model_name: str = 'unsloth/qwen3-4b-instruct-2507'
    embedding_model_name: str = 'unsloth/qwen3-4b-instruct-2507'
    base_url: str = 'http://localhost:1234/v1'
    api_key: str = 'lmstudio'
    max_auto_turns: int = 24
    max_tool_output: int = 20000
    tool_timeout_seconds: int = 5
    done_token: str = '__DONE__'
    skill_metadata_dir: str = 'skill_catalog/metadatas'
    skill_procedure_dir: str = 'skill_catalog/procedures'
    skill_index_dir: str = 'skills/indexes'
    skill_stats_filename: str = 'skills.stats.json'
    run_trace_enabled: bool = True
    run_trace_payloads: bool = False
    run_trace_dir: str = 'logs/runs'


def build_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    provider = configured_provider(env)
    default_model = chat_model_name(provider, env)
    return Settings(
        host=env.get('WALLACE_HOST', '127.0.0.1'),
        project_dir=Path(env.get('WALLACE_PROJECT_DIR', '/opt/wallace')),
        port=env_int('WALLACE_PORT', 8000, env=env),
        sandbox_dir=Path(env.get('WALLACE_SANDBOX_DIR', '/opt/wallace/sandbox')),
        curl_whitelist_path=Path(env.get('WALLACE_CURL_WHITELIST_PATH', '/var/lib/wallace/curl_whitelist.json')),
        model_provider=provider,
        model_name=default_model,
        embedding_model_name=env_text('WALLACE_EMBEDDING_MODEL', default_model, env),
        base_url=chat_base_url(provider, env),
        api_key=chat_api_key(provider, env),
        max_auto_turns=env_int('WALLACE_MAX_AUTO_TURNS', 24, env=env),
        max_tool_output=env_int('WALLACE_MAX_TOOL_OUTPUT', 20000, env=env),
        tool_timeout_seconds=env_int('WALLACE_TOOL_TIMEOUT', 5, env=env),
        done_token=env.get('WALLACE_DONE_TOKEN', '__DONE__'),
        skill_metadata_dir=env.get('WALLACE_SKILL_METADATA_DIR', 'skill_catalog/metadatas'),
        skill_procedure_dir=env.get('WALLACE_SKILL_PROCEDURE_DIR', 'skill_catalog/procedures'),
        skill_index_dir=env.get('WALLACE_SKILL_INDEX_DIR', 'skills/indexes'),
        skill_stats_filename=env.get('WALLACE_SKILL_STATS_FILENAME', 'skills.stats.json'),
        run_trace_enabled=env_bool('WALLACE_RUN_TRACE', True, env),
        run_trace_payloads=env_bool('WALLACE_RUN_TRACE_PAYLOADS', False, env),
        run_trace_dir=env.get('WALLACE_RUN_TRACE_DIR', 'logs/runs'),
    )


SETTINGS = build_settings()
