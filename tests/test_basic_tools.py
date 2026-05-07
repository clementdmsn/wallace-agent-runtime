from __future__ import annotations

import sandbox
from config import Settings
from tools import basic_tools
from tools.basic_tools import (
    append_to_file,
    find_file,
    read_file,
    read_file_with_line_numbers,
    remove_file,
    replace_in_file,
    run_shell,
    write_file,
)
from tests.conftest import settings_for_sandbox


def configure_sandbox(tmp_path, monkeypatch):
    settings = settings_for_sandbox(tmp_path)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(basic_tools, 'SETTINGS', settings)
    return settings


def test_remove_file_deletes_existing_file(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    write_result = write_file('tmp/delete-me.txt', 'hello')

    remove_result = remove_file('tmp/delete-me.txt')
    read_result = read_file('tmp/delete-me.txt')

    assert write_result['status'] == 'ok'
    assert remove_result == {
        'status': 'ok',
        'path': 'tmp/delete-me.txt',
        'message': 'file removed',
    }
    assert read_result['status'] == 'error'
    assert read_result['error'] == 'file does not exist'


def test_remove_file_rejects_directories(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    (tmp_path / 'tmp').mkdir()

    result = remove_file('tmp')

    assert result['status'] == 'error'
    assert result['error'] == 'path is a directory'


def test_remove_file_rejects_missing_file(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)

    result = remove_file('missing.txt')

    assert result['status'] == 'error'
    assert result['error'] == 'file does not exist'


def test_find_file_returns_relative_matches(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    write_file('snake.py', 'root')
    write_file('games/snake.py', 'nested')
    write_file('games/other.py', 'other')

    result = find_file('snake.py')

    assert result == {
        'status': 'ok',
        'name': 'snake.py',
        'root': '.',
        'matches': ['games/snake.py', 'snake.py'],
        'count': 2,
    }


def test_find_file_rejects_path_like_name(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)

    result = find_file('games/snake.py')

    assert result['status'] == 'error'
    assert result['error'] == 'name must be a filename, not a path'


def test_read_write_append_and_replace_file(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)

    write_result = write_file('notes/todo.txt', 'one')
    append_result = append_to_file('notes/todo.txt', 'two')
    read_result = read_file('notes/todo.txt')
    replace_result = replace_in_file('notes/todo.txt', 'one\ntwo', 'done')
    updated = read_file('notes/todo.txt')

    assert write_result['status'] == 'ok'
    assert write_result['created'] is True
    assert append_result['status'] == 'ok'
    assert read_result['content'] == 'one\ntwo'
    assert replace_result['status'] == 'ok'
    assert updated['content'] == 'done'


def test_read_file_reports_truncated_content(tmp_path, monkeypatch):
    settings = Settings(sandbox_dir=tmp_path, max_tool_output=5)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(basic_tools, 'SETTINGS', settings)
    write_file('notes/long.txt', '123456789')

    result = read_file('notes/long.txt')

    assert result['status'] == 'ok'
    assert result['content'] == '12345'
    assert result['truncated'] is True


def test_read_file_with_line_numbers_returns_precise_evidence(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    write_file('app.py', 'first\nsecond\n')

    result = read_file_with_line_numbers('app.py')

    assert result['status'] == 'ok'
    assert result['content'] == '1: first\n2: second\n'
    assert result['line_numbered'] is True


def test_append_to_file_does_not_read_existing_file_to_append(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    write_file('notes/large.txt', 'one')

    result = append_to_file('notes/large.txt', 'two')

    assert result['status'] == 'ok'
    assert read_file('notes/large.txt')['content'] == 'one\ntwo'


def test_replace_file_rejects_missing_or_ambiguous_search(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    write_file('notes.txt', 'same\nsame\n')

    missing = replace_in_file('missing.txt', 'x', 'y')
    no_match = replace_in_file('notes.txt', 'absent', 'new')
    ambiguous = replace_in_file('notes.txt', 'same', 'new')

    assert missing['error'] == 'file does not exist'
    assert no_match['error'] == 'search text not found'
    assert ambiguous['error'] == 'search text matched multiple locations; provide a more specific block'
    assert ambiguous['replacements'] == 2


def test_file_tools_reject_directories_and_unsafe_paths(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    (tmp_path / 'dir').mkdir()

    assert read_file('dir')['error'] == 'path is a directory'
    assert replace_in_file('dir', 'a', 'b')['error'] == 'path is a directory'
    assert write_file('../escape.txt', 'x')['status'] == 'error'
    assert append_to_file('../escape.txt', 'x')['status'] == 'error'


def test_find_file_rejects_bad_roots(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    write_file('file.txt', 'content')

    assert find_file('')['error'] == 'name must be a non-empty string'
    assert find_file('file.txt', root='missing')['error'] == 'root does not exist'
    assert find_file('file.txt', root='file.txt')['error'] == 'root is not a directory'


def test_run_shell_executes_allowed_commands_and_reports_failures(tmp_path, monkeypatch):
    configure_sandbox(tmp_path, monkeypatch)
    write_file('hello.txt', 'hello')

    ok = run_shell('cat hello.txt')
    blocked = run_shell('python -c "print(1)"')
    missing = run_shell('cat missing.txt')

    assert ok['status'] == 'ok'
    assert ok['stdout'] == 'hello'
    assert blocked['status'] == 'error'
    assert 'command not allowed' in blocked['error']
    assert missing['status'] == 'ok'
    assert missing['returncode'] != 0


def test_run_shell_reports_truncated_stdout(tmp_path, monkeypatch):
    settings = Settings(sandbox_dir=tmp_path, max_tool_output=5)
    monkeypatch.setattr(sandbox, 'SETTINGS', settings)
    monkeypatch.setattr(basic_tools, 'SETTINGS', settings)
    write_file('long.txt', '123456789')

    result = run_shell('cat long.txt')

    assert result['status'] == 'ok'
    assert result['stdout'] == '12345'
    assert result['stdout_truncated'] is True
    assert result['stderr_truncated'] is False
