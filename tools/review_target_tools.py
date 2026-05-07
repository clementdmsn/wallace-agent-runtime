from __future__ import annotations

from pathlib import Path
from typing import Any

from sandbox import safe_path


REVIEW_TARGET_EXTENSIONS = {
    '.c',
    '.cc',
    '.cfg',
    '.conf',
    '.cpp',
    '.cs',
    '.css',
    '.env',
    '.go',
    '.h',
    '.hpp',
    '.html',
    '.ini',
    '.java',
    '.js',
    '.json',
    '.jsx',
    '.kt',
    '.lock',
    '.md',
    '.php',
    '.properties',
    '.py',
    '.rb',
    '.rs',
    '.sh',
    '.toml',
    '.ts',
    '.tsx',
    '.xml',
    '.yaml',
    '.yml',
}

REVIEW_TARGET_FILENAMES = {
    '.env',
    'Dockerfile',
    'Makefile',
    'Pipfile',
    'Pipfile.lock',
    'composer.json',
    'composer.lock',
    'go.mod',
    'go.sum',
    'package-lock.json',
    'package.json',
    'pnpm-lock.yaml',
    'poetry.lock',
    'pyproject.toml',
    'requirements.txt',
    'requirements-dev.txt',
    'yarn.lock',
}

SKIPPED_REVIEW_DIRS = {
    '.cache',
    '.git',
    '.hg',
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
    '.svn',
    '.tox',
    '.venv',
    '__pycache__',
    'build',
    'coverage',
    'dist',
    'node_modules',
    'target',
    'vendor',
    'venv',
}


def _is_review_target(path: Path) -> bool:
    return path.name in REVIEW_TARGET_FILENAMES or path.suffix.lower() in REVIEW_TARGET_EXTENSIONS


def _relative_to_sandbox(path: Path) -> str:
    sandbox_root = safe_path('.')
    return path.relative_to(sandbox_root).as_posix()


def discover_review_targets(root: str = '.', max_files: int = 20) -> dict[str, Any]:
    try:
        if not isinstance(root, str) or not root.strip():
            return {'status': 'error', 'error': 'root must be a non-empty string'}
        if not isinstance(max_files, int) or max_files <= 0:
            return {'status': 'error', 'error': 'max_files must be a positive integer'}

        root_path = safe_path(root)
        if not root_path.exists():
            return {'status': 'error', 'root': root, 'error': 'root does not exist'}

        if root_path.is_file():
            if not _is_review_target(root_path):
                return {
                    'status': 'ok',
                    'root': root,
                    'targets': [],
                    'count': 0,
                    'truncated': False,
                    'message': 'file extension is not in the review target allowlist',
                }
            stat = root_path.stat()
            return {
                'status': 'ok',
                'root': root,
                'targets': [
                    {
                        'path': _relative_to_sandbox(root_path),
                        'kind': 'file',
                        'suffix': root_path.suffix.lower(),
                        'size_bytes': stat.st_size,
                    }
                ],
                'count': 1,
                'truncated': False,
            }

        if not root_path.is_dir():
            return {'status': 'error', 'root': root, 'error': 'root is neither a file nor a directory'}

        candidates: list[Path] = []
        stack = [root_path]
        while stack:
            current = stack.pop()
            try:
                children = sorted(current.iterdir(), key=lambda item: item.name.lower())
            except OSError:
                continue
            for child in children:
                if child.is_dir():
                    if child.name in SKIPPED_REVIEW_DIRS:
                        continue
                    stack.append(child)
                    continue
                if child.is_file() and _is_review_target(child):
                    candidates.append(child)

        candidates.sort(key=lambda item: _relative_to_sandbox(item))
        limited = candidates[:max_files]
        targets = [
            {
                'path': _relative_to_sandbox(path),
                'kind': 'file',
                'suffix': path.suffix.lower(),
                'size_bytes': path.stat().st_size,
            }
            for path in limited
        ]

        return {
            'status': 'ok',
            'root': root,
            'targets': targets,
            'count': len(targets),
            'total_candidates': len(candidates),
            'truncated': len(candidates) > len(limited),
            'max_files': max_files,
            'skipped_directories': sorted(SKIPPED_REVIEW_DIRS),
        }
    except Exception as exc:
        return {'status': 'error', 'root': root, 'error': str(exc)}
