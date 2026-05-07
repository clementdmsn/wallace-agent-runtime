from __future__ import annotations

import json
import os
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from config import SETTINGS

SENSITIVE_KEYS = {
    'api_key',
    'apikey',
    'authorization',
    'password',
    'secret',
    'token',
}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return str(value)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_KEYS:
                redacted[key_text] = '[redacted]'
            else:
                redacted[key_text] = _redact(item)
        return redacted
    if isinstance(value, (list, tuple, set)):
        return [_redact(item) for item in value]
    return value


class RunTrace:
    def __init__(self, run_id: int):
        trace_dir = Path(SETTINGS.run_trace_dir)
        if not trace_dir.is_absolute():
            trace_dir = SETTINGS.sandbox_dir / trace_dir
        trace_dir.mkdir(parents=True, exist_ok=True)

        self.run_id = run_id
        self.created_ns = time.time_ns()
        self.pid = os.getpid()
        self.trace_id = f'{run_id:06d}-{self.created_ns}-{uuid.uuid4().hex[:8]}'
        self.payloads_enabled = SETTINGS.run_trace_payloads
        wall_time = time.strftime('%Y%m%dT%H%M%S%z', time.localtime(self.created_ns / 1_000_000_000))
        self.path = trace_dir / f'run-{run_id:06d}-{wall_time}-{self.created_ns}-{self.pid}-{self.trace_id[-8:]}.jsonl'

    @classmethod
    def start(cls, run_id: int) -> RunTrace | None:
        if not SETTINGS.run_trace_enabled:
            return None
        try:
            trace = cls(run_id)
            trace.record(
                'trace_started',
                path=str(trace.path),
                pid=trace.pid,
                created_ns=trace.created_ns,
            )
            return trace
        except Exception:
            return None

    def payload(self, value: Any) -> Any:
        if not self.payloads_enabled:
            return '[payload logging disabled]'
        return deepcopy(_redact(_json_safe(value)))

    def record(self, event: str, **fields: Any) -> None:
        line = {
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'event': event,
            'run_id': self.run_id,
            'trace_id': self.trace_id,
            **_json_safe(fields),
        }
        try:
            with self.path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + '\n')
        except Exception:
            pass
