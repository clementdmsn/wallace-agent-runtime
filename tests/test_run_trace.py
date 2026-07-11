from __future__ import annotations

import json
import logging

import agent.run_trace as run_trace
from tests.conftest import settings_for_sandbox


def test_run_trace_writes_jsonl_events(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    settings = settings.__class__(
        sandbox_dir=settings.sandbox_dir,
        run_trace_payloads=True,
    )
    monkeypatch.setattr(run_trace, 'SETTINGS', settings)

    trace = run_trace.RunTrace.start(12)

    assert trace is not None
    trace.record('example_event', payload=trace.payload({'value': 'ok'}))

    lines = trace.path.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 2
    started = json.loads(lines[0])
    assert started['event'] == 'trace_started'
    assert started['trace_id'] == trace.trace_id
    assert started['pid'] == trace.pid
    assert started['created_ns'] == trace.created_ns
    event = json.loads(lines[1])
    assert event['event'] == 'example_event'
    assert event['run_id'] == 12
    assert event['trace_id'] == trace.trace_id
    assert event['payload'] == {'value': 'ok'}


def test_run_trace_redacts_sensitive_payload_fields(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    settings = settings.__class__(
        sandbox_dir=settings.sandbox_dir,
        run_trace_payloads=True,
    )
    monkeypatch.setattr(run_trace, 'SETTINGS', settings)

    trace = run_trace.RunTrace.start(14)

    assert trace is not None
    assert trace.payload({
        'messages': [{'role': 'user', 'content': 'secret text'}],
        'safe': {'value': 'ok'},
        'api_key': 'secret-key',
    }) == {
        'messages': [{'role': 'user', 'content': 'secret text'}],
        'safe': {'value': 'ok'},
        'api_key': '[redacted]',
    }


def test_run_trace_can_disable_payloads(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    settings = settings.__class__(
        sandbox_dir=settings.sandbox_dir,
        run_trace_payloads=False,
    )
    monkeypatch.setattr(run_trace, 'SETTINGS', settings)

    trace = run_trace.RunTrace.start(13)

    assert trace is not None
    assert trace.payload({'secret': 'value'}) == '[payload logging disabled]'


def test_run_trace_paths_are_unique_for_reused_run_ids(monkeypatch, tmp_path):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(run_trace, 'SETTINGS', settings)

    first = run_trace.RunTrace.start(1)
    second = run_trace.RunTrace.start(1)

    assert first is not None
    assert second is not None
    assert first.path != second.path
    assert first.trace_id != second.trace_id
    assert first.path.exists()
    assert second.path.exists()


def test_run_trace_skips_invalid_events_without_crashing(monkeypatch, tmp_path, caplog):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(run_trace, 'SETTINGS', settings)

    trace = run_trace.RunTrace.start(15)

    assert trace is not None
    with caplog.at_level(logging.WARNING, logger='agent.run_trace'):
        trace.record('', payload={'value': 'bad'})

    lines = trace.path.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])['event'] == 'trace_started'
    assert trace.error_count == 1
    assert 'invalid run trace event skipped' in caplog.text


def test_run_trace_rejects_reserved_dynamic_fields(monkeypatch, tmp_path, caplog):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(run_trace, 'SETTINGS', settings)

    trace = run_trace.RunTrace.start(16)

    assert trace is not None
    with caplog.at_level(logging.WARNING, logger='agent.run_trace'):
        trace.record('example_event', run_id=999)

    lines = trace.path.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 1
    assert trace.error_count == 1
    assert 'trace fields contain reserved keys' in caplog.text


def test_run_trace_write_failures_are_nonfatal(monkeypatch, tmp_path, caplog):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(run_trace, 'SETTINGS', settings)

    trace = run_trace.RunTrace.start(17)

    assert trace is not None
    trace.path = tmp_path / 'missing' / 'run.jsonl'
    with caplog.at_level(logging.WARNING, logger='agent.run_trace'):
        trace.record('example_event', payload={'value': 'ok'})

    assert trace.error_count == 1
    assert 'failed to write run trace event' in caplog.text
