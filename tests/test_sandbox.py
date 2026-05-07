from __future__ import annotations

import pytest

import sandbox
from sandbox import configured_project_path, configured_sandbox_path, safe_path, validate_command
from tests.conftest import settings_for_sandbox


def test_safe_path_resolves_inside_configured_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, 'SETTINGS', settings_for_sandbox(tmp_path))

    resolved = safe_path('notes/todo.md')

    assert resolved == tmp_path / 'notes' / 'todo.md'
    assert tmp_path.exists()


@pytest.mark.parametrize(
    'path',
    [
        '',
        '/tmp/file.txt',
        '../file.txt',
        'nested/../file.txt',
        '~/file.txt',
    ],
)
def test_safe_path_rejects_unsafe_paths(tmp_path, monkeypatch, path):
    monkeypatch.setattr(sandbox, 'SETTINGS', settings_for_sandbox(tmp_path))

    with pytest.raises(ValueError):
        safe_path(path)


def test_configured_sandbox_path_accepts_absolute_path_inside_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, 'SETTINGS', settings_for_sandbox(tmp_path))

    resolved = configured_sandbox_path(str(tmp_path / 'skills' / 'metadatas'))

    assert resolved == tmp_path / 'skills' / 'metadatas'


def test_configured_sandbox_path_rejects_absolute_path_outside_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, 'SETTINGS', settings_for_sandbox(tmp_path))

    with pytest.raises(ValueError, match='escapes sandbox'):
        configured_sandbox_path('/tmp/outside')


def test_configured_project_path_accepts_absolute_path_inside_project(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, 'SETTINGS', settings_for_sandbox(tmp_path))

    resolved = configured_project_path(str(tmp_path / 'skill_catalog' / 'metadatas'))

    assert resolved == tmp_path / 'skill_catalog' / 'metadatas'


def test_configured_project_path_rejects_absolute_path_outside_project(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, 'SETTINGS', settings_for_sandbox(tmp_path))

    with pytest.raises(ValueError, match='escapes project'):
        configured_project_path('/tmp/outside')


def test_validate_command_accepts_allowed_command():
    assert validate_command('ls -la') == ['ls', '-la']
    assert validate_command('find . -name "*.py"') == ['find', '.', '-name', '*.py']
    assert validate_command('grep -n needle notes.txt') == ['grep', '-n', 'needle', 'notes.txt']


@pytest.mark.parametrize(
    'command',
    [
        'rm file.txt',
        'python -c "print(1)"',
        'cat ../secret.txt',
        'echo ok && echo bad',
        'cat /etc/passwd',
        'cat /tmp/secret.txt',
        'find ..',
        'cp file.txt ..',
        'mv file.txt nested/..',
        'cat ~/secret.txt',
        'sed -n 1p notes.txt',
        'find . -exec cat {} ;',
        'find . -delete',
        'find . -ok cat {} ;',
        'grep --include=*.py needle .',
        'ls --hyperlink',
        'pwd .',
    ],
)
def test_validate_command_rejects_blocked_or_unknown_commands(command):
    with pytest.raises(ValueError):
        validate_command(command)
