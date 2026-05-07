from pathlib import Path
import shlex

from config import SETTINGS


ALLOWED_COMMANDS = {
    'ls', 'pwd', 'cat', 'touch', 'mv', 'cp', 'mkdir',
    'find', 'grep', 'head', 'tail', 'wc', 'printf', 'echo'
}

CONTROL_TOKENS = {'&&', '||', ';', '|', '>', '>>', '<', '<<', '&'}
FIND_BLOCKED_PREDICATES = {'-exec', '-execdir', '-ok', '-okdir', '-delete', '-fls', '-fprint', '-fprintf'}
READ_COMMANDS = {'cat', 'head', 'tail', 'wc'}
PATH_MUTATION_COMMANDS = {'touch', 'mv', 'cp', 'mkdir'}


def ensure_sandbox_dir() -> None:
    SETTINGS.sandbox_dir.mkdir(parents=True, exist_ok=True)


# Resolve a user-provided relative path under the configured sandbox.
def safe_path(path: str) -> Path:
    if not isinstance(path, str):
        raise ValueError('path must be a string')
    cleaned = path.strip()
    if not cleaned:
        raise ValueError('empty path')
    if cleaned.startswith('/'):
        raise ValueError('absolute paths are not allowed')
    if '..' in cleaned.split('/'):
        raise ValueError('parent directory access is not allowed')
    if '~' in cleaned:
        raise ValueError('home expansion is not allowed')

    ensure_sandbox_dir()
    full = (SETTINGS.sandbox_dir / cleaned).resolve()
    try:
        full.relative_to(SETTINGS.sandbox_dir.resolve())
    except ValueError as exc:
        raise ValueError('path escapes sandbox') from exc
    return full


def configured_sandbox_path(path: str) -> Path:
    if not isinstance(path, str):
        raise ValueError('path must be a string')
    cleaned = path.strip()
    if not cleaned:
        raise ValueError('empty path')

    ensure_sandbox_dir()
    sandbox_root = SETTINGS.sandbox_dir.resolve()
    candidate = Path(cleaned).expanduser()
    full = candidate.resolve() if candidate.is_absolute() else (sandbox_root / candidate).resolve()
    try:
        full.relative_to(sandbox_root)
    except ValueError as exc:
        raise ValueError('configured path escapes sandbox') from exc
    return full


def configured_project_path(path: str) -> Path:
    if not isinstance(path, str):
        raise ValueError('path must be a string')
    cleaned = path.strip()
    if not cleaned:
        raise ValueError('empty path')

    project_root = SETTINGS.project_dir.resolve()
    candidate = Path(cleaned).expanduser()
    full = candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()
    try:
        full.relative_to(project_root)
    except ValueError as exc:
        raise ValueError('configured path escapes project') from exc
    return full


def project_relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(SETTINGS.project_dir.resolve()).as_posix()
    except Exception:
        return str(path)


def _validate_path_arg(arg: str) -> None:
    if arg.startswith('-'):
        return
    safe_path(arg)


def _validate_option(arg: str, *, allowed: set[str], command: str) -> None:
    if not arg.startswith('-'):
        return
    if arg == '--':
        return
    if arg not in allowed and not (
        len(arg) > 2 and arg.startswith('-') and set(arg[1:]) <= set(''.join(item.lstrip('-') for item in allowed))
    ):
        raise ValueError(f'option not allowed for {command}: {arg}')


def _validate_find_args(args: list[str]) -> None:
    for arg in args:
        if arg in FIND_BLOCKED_PREDICATES:
            raise ValueError(f'find predicate not allowed: {arg}')
        if arg in {'+', r'\;'}:
            raise ValueError(f'find terminator not allowed: {arg}')
        if arg.startswith('/') or arg.startswith('~') or '..' in arg.split('/'):
            raise ValueError('unsafe find path or pattern')


def _validate_grep_args(args: list[str]) -> None:
    allowed_options = {'-n', '-i', '-r', '-R', '-l', '-H', '-h', '-s'}
    after_double_dash = False
    for arg in args:
        if arg == '--':
            after_double_dash = True
            continue
        if not after_double_dash and arg.startswith('-'):
            _validate_option(arg, allowed=allowed_options, command='grep')
            continue
        if arg.startswith('/') or arg.startswith('~') or '..' in arg.split('/'):
            raise ValueError('unsafe grep argument')


def _validate_path_command(command_name: str, args: list[str]) -> None:
    option_sets = {
        'ls': {'-a', '-l', '-h', '-t', '-r', '-R', '-la', '-al'},
        'head': {'-n'},
        'tail': {'-n', '-f'},
        'wc': {'-l', '-w', '-c', '-m'},
        'mkdir': {'-p'},
        'cp': {'-r', '-R', '-p', '-f'},
        'mv': {'-f'},
    }
    allowed_options = option_sets.get(command_name, set())
    skip_next_value_for = {'head': {'-n'}, 'tail': {'-n'}}
    skip_next = False
    for arg in args:
        if skip_next:
            if not arg.isdigit():
                raise ValueError(f'{command_name} numeric option value must be an integer')
            skip_next = False
            continue
        if arg.startswith('-'):
            _validate_option(arg, allowed=allowed_options, command=command_name)
            if arg in skip_next_value_for.get(command_name, set()):
                skip_next = True
            continue
        _validate_path_arg(arg)


def validate_command(command: str) -> list[str]:
    if not isinstance(command, str):
        raise ValueError('command must be a string')

    command = command.strip()
    if not command:
        raise ValueError('empty command')

    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f'invalid shell syntax: {exc}') from exc

    if not parts:
        raise ValueError('empty command')

    if parts[0] not in ALLOWED_COMMANDS:
        raise ValueError(f'command not allowed: {parts[0]}')

    if any(part in CONTROL_TOKENS for part in parts):
        raise ValueError('shell control operators are not allowed')

    command_name = parts[0]
    args = parts[1:]

    if command_name == 'pwd':
        if args:
            raise ValueError('pwd does not accept arguments')
    elif command_name == 'find':
        _validate_find_args(args)
    elif command_name == 'grep':
        _validate_grep_args(args)
    elif command_name in READ_COMMANDS | PATH_MUTATION_COMMANDS | {'ls'}:
        _validate_path_command(command_name, args)
    elif command_name in {'echo', 'printf'}:
        for arg in args:
            if arg.startswith('/') or arg.startswith('~') or '..' in arg.split('/'):
                raise ValueError(f'unsafe {command_name} argument')

    return parts
