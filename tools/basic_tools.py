from __future__ import annotations

import subprocess
import tempfile
from typing import Any

from config import SETTINGS
from sandbox import ensure_sandbox_dir, safe_path, validate_command


# Basic tools are deliberately narrow wrappers around sandbox-validated file and
# shell operations. Destructive actions should stay explicit, not shell-generic.
def truncate(text: str) -> str:
    return text[: SETTINGS.max_tool_output]


def read_limited_text_file(path_or_fd) -> tuple[str, bool]:
    max_bytes = SETTINGS.max_tool_output
    if isinstance(path_or_fd, int):
        with open(path_or_fd, 'rb', closefd=False) as handle:
            data = handle.read(max_bytes + 1)
    else:
        with open(path_or_fd, 'rb') as handle:
            data = handle.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]
    return data.decode('utf-8', errors='replace'), truncated


def run_shell(command: str) -> dict[str, Any]:
    try:
        parts = validate_command(command)
        ensure_sandbox_dir()
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                parts,
                cwd=str(SETTINGS.sandbox_dir),
                stdout=stdout_file,
                stderr=stderr_file,
                text=False,
            )
            try:
                process.wait(timeout=SETTINGS.tool_timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                return {
                    'status': 'error',
                    'command': command,
                    'error': f'command timed out after {SETTINGS.tool_timeout_seconds} seconds',
                }

            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout, stdout_truncated = read_limited_text_file(stdout_file.fileno())
            stderr, stderr_truncated = read_limited_text_file(stderr_file.fileno())

            return {
                'status': 'ok',
                'command': command,
                'returncode': process.returncode,
                'stdout': stdout,
                'stderr': stderr,
                'stdout_truncated': stdout_truncated,
                'stderr_truncated': stderr_truncated,
            }
    except subprocess.TimeoutExpired:
        return {
            'status': 'error',
            'command': command,
            'error': f'command timed out after {SETTINGS.tool_timeout_seconds} seconds',
        }
    except Exception as exc:
        return {'status': 'error', 'command': command, 'error': str(exc)}


def read_file(path: str) -> dict[str, Any]:
    try:
        full = safe_path(path)
        if not full.exists():
            return {'status': 'error', 'path': path, 'error': 'file does not exist'}
        if full.is_dir():
            return {'status': 'error', 'path': path, 'error': 'path is a directory'}
        content, truncated = read_limited_text_file(full)
        return {'status': 'ok', 'path': path, 'content': content, 'truncated': truncated}
    except Exception as exc:
        return {'status': 'error', 'path': path, 'error': str(exc)}


def read_file_with_line_numbers(path: str) -> dict[str, Any]:
    result = read_file(path)
    if result.get('status') != 'ok':
        return result

    original_content = str(result.get('content', ''))
    trailing_newline = original_content.endswith('\n')
    content = original_content.rstrip('\n')
    numbered = '\n'.join(
        f'{line_number}: {line}'
        for line_number, line in enumerate(content.splitlines(), start=1)
    )
    if trailing_newline and numbered:
        numbered += '\n'

    return {
        **result,
        'content': numbered,
        'line_numbered': True,
    }


def write_file(path: str, content: str) -> dict[str, Any]:
    try:
        full = safe_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        existed = full.exists()
        full.write_text(content, encoding='utf-8')
        return {
            'status': 'ok',
            'path': path,
            'created': not existed,
            'bytes_written': len(content.encode('utf-8')),
            'message': 'file written',
        }
    except Exception as exc:
        return {'status': 'error', 'path': path, 'error': str(exc)}


def append_to_file(path: str, content: str) -> dict[str, Any]:
    try:
        full = safe_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        existed = full.exists()
        needs_separator = existed and full.stat().st_size > 0
        with full.open('a', encoding='utf-8') as handle:
            if needs_separator:
                handle.write('\n')
            handle.write(content)
        return {
            'status': 'ok',
            'path': path,
            'created': not existed,
            'bytes_written': full.stat().st_size,
            'message': 'appended to file',
        }
    except Exception as exc:
        return {'status': 'error', 'path': path, 'error': str(exc)}


def replace_in_file(path: str, search: str, replace: str) -> dict[str, Any]:
    try:
        full = safe_path(path)
        if not full.exists():
            return {'status': 'error', 'path': path, 'error': 'file does not exist'}
        if full.is_dir():
            return {'status': 'error', 'path': path, 'error': 'path is a directory'}

        content = full.read_text(encoding='utf-8')
        count = content.count(search)
        if count == 0:
            return {'status': 'error', 'path': path, 'error': 'search text not found'}
        if count > 1:
            return {
                'status': 'error',
                'path': path,
                'error': 'search text matched multiple locations; provide a more specific block',
                'replacements': count,
            }

        updated = content.replace(search, replace, 1)
        full.write_text(updated, encoding='utf-8')
        return {
            'status': 'ok',
            'path': path,
            'replacements': 1,
            'bytes_written': len(updated.encode('utf-8')),
            'message': 'file updated',
        }
    except Exception as exc:
        return {'status': 'error', 'path': path, 'error': str(exc)}


def remove_file(path: str) -> dict[str, Any]:
    try:
        full = safe_path(path)
        if not full.exists():
            return {'status': 'error', 'path': path, 'error': 'file does not exist'}
        if full.is_dir():
            return {'status': 'error', 'path': path, 'error': 'path is a directory'}
        full.unlink()
        return {'status': 'ok', 'path': path, 'message': 'file removed'}

    except Exception as exc:
        return {'status': 'error', 'path': path, 'error': str(exc)}


def find_file(name: str, root: str = '.') -> dict[str, Any]:
    try:
        if not isinstance(name, str) or not name.strip():
            return {'status': 'error', 'error': 'name must be a non-empty string'}

        name = name.strip()
        if '/' in name or '\\' in name:
            return {'status': 'error', 'name': name, 'error': 'name must be a filename, not a path'}

        root_path = safe_path(root)
        if not root_path.exists():
            return {'status': 'error', 'name': name, 'root': root, 'error': 'root does not exist'}
        if not root_path.is_dir():
            return {'status': 'error', 'name': name, 'root': root, 'error': 'root is not a directory'}

        sandbox_root = safe_path('.')
        matches = [
            path.relative_to(sandbox_root).as_posix()
            for path in root_path.rglob(name)
            if path.is_file()
        ]

        return {
            'status': 'ok',
            'name': name,
            'root': root,
            'matches': sorted(matches),
            'count': len(matches),
        }
    except Exception as exc:
        return {'status': 'error', 'name': name, 'root': root, 'error': str(exc)}
