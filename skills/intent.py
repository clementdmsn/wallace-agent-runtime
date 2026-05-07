from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable


ACTION_KEYWORDS: dict[str, frozenset[str]] = {
    'create': frozenset({'create', 'make', 'build', 'generate', 'write'}),
    'summarize': frozenset({'summarize', 'summary', 'describe', 'explain', 'overview'}),
    'review': frozenset({'review', 'audit', 'inspect'}),
    'debug': frozenset({'debug', 'troubleshoot'}),
    'edit': frozenset({'edit', 'modify', 'change', 'refactor', 'rewrite', 'update'}),
    'delete': frozenset({'delete', 'remove'}),
    'learn': frozenset({'learn', 'memorize'}),
}

QUESTION_STARTERS = frozenset({
    'what', 'why', 'how', 'which', 'when', 'where', 'who', 'whom', 'whose',
    'quoi', 'pourquoi', 'comment', 'quel', 'quelle', 'quels', 'quelles', 'quand', 'ou', 'où', 'qui',
})

COMMAND_STARTERS = frozenset().union(*ACTION_KEYWORDS.values(), {
    'add', 'append', 'clean', 'fix', 'run', 'test', 'implement', 'install', 'move',
    'rename', 'replace', 'debug', 'check', 'find', 'list',
})


# Intent parsing is intentionally conservative. It extracts only the arguments
# needed to route skills and avoids inventing symbols from file-only requests.
def normalize_text(text: str) -> str:
    lowered = text.lower()
    for char in ',:;()[]{}':
        lowered = lowered.replace(char, ' ')
    return ' '.join(lowered.split())


def extract_action(tokens: set[str]) -> str:
    for action, keywords in ACTION_KEYWORDS.items():
        if tokens & keywords:
            return action
    return 'unknown'


def extract_speech_act(user_text: str, normalized_text: str) -> str:
    tokens = normalized_text.split()
    first = tokens[0] if tokens else ''

    has_question_mark = '?' in user_text
    starts_question = first in QUESTION_STARTERS
    starts_command = first in COMMAND_STARTERS
    polite_command = first == 'please' and len(tokens) > 1 and tokens[1] in COMMAND_STARTERS
    collaborative_command = len(tokens) > 1 and tokens[0] in {'lets', "let's"} and tokens[1] in COMMAND_STARTERS

    if (has_question_mark or starts_question) and (starts_command or polite_command or collaborative_command):
        return 'mixed'
    if has_question_mark or starts_question:
        return 'question'
    if starts_command or polite_command or collaborative_command:
        return 'command'
    return 'unknown'


def extract_args(tokens: Iterable[str]) -> dict[str, str]:
    args: dict[str, str] = {}

    for token in tokens:
        cleaned = token.strip("\"'`,:;()[]{}")
        if (
            cleaned.startswith(('./', '../', '/'))
            or cleaned.endswith('/')
            or '/' in cleaned
            or '\\' in cleaned
        ):
            args['path'] = cleaned.rstrip('/')
            break

        cleaned = cleaned.strip('.')
        if '.' not in cleaned or cleaned.startswith('.'):
            continue

        suffix = Path(cleaned).suffix.lower()
        if suffix in {
            '.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.md', '.html', '.css',
            '.java', '.go', '.rs', '.php', '.rb', '.c', '.cpp', '.h', '.hpp', '.sh',
        }:
            args['path'] = cleaned
            break

    return args


def is_symbol_candidate(token: str, path: str | None = None) -> bool:
    if not token:
        return False
    if token in {'a', 'an', 'the', 'function', 'method', 'symbol', 'called', 'named', 'in', 'from', 'of', 'this', 'file', 'code'}:
        return False
    if token in {'explain', 'summarize', 'summary', 'overview', 'describe', 'look', 'at'}:
        return False
    if '.' in token or '/' in token or '\\' in token:
        return False
    if path and token == Path(path).stem.lower():
        return False
    return token.replace('_', '').isalnum()


def extract_symbol_arg(intent_text: str, arguments: dict[str, Any] | None = None) -> str | None:
    # A symbol is trusted only when the user ties it to function/method/symbol wording.
    arguments = arguments or {}
    normalized = normalize_text(intent_text)
    tokens = normalized.split()
    path = arguments.get('path') if isinstance(arguments.get('path'), str) else None
    markers = {'function', 'method', 'symbol'}

    if path:
        pattern = re.compile(
            r'\b(?:debug|troubleshoot|check|inspect|analyze)\s+'
            r'([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\s*\))?\s+'
            r'(?:in|from|of)\s+'
            + re.escape(path),
            re.IGNORECASE,
        )
        match = pattern.search(intent_text)
        if match:
            candidate = match.group(1).lower()
            if is_symbol_candidate(candidate, path):
                return candidate

    for i, token in enumerate(tokens):
        if token not in markers:
            continue

        if i + 1 < len(tokens):
            candidate = tokens[i + 1].strip("\'\"`.,:;()[]{}")
            if candidate in {'called', 'named'} and i + 2 < len(tokens):
                candidate = tokens[i + 2].strip("\'\"`.,:;()[]{}")
            if is_symbol_candidate(candidate, path):
                return candidate

        if i > 0:
            candidate = tokens[i - 1].strip("\'\"`.,:;()[]{}")
            if is_symbol_candidate(candidate, path):
                return candidate

    return None


def extract_filetype(args: dict[str, str]) -> str | None:
    path = args.get('path')
    if not path:
        return None
    suffix = Path(path).suffix.lower()
    return suffix[1:] if suffix.startswith('.') else suffix


def extract_domain(tokens: set[str], filetype: str | None) -> str:
    if filetype in {'py', 'js', 'jsx', 'ts', 'tsx', 'java', 'go', 'rs', 'php', 'rb', 'c', 'cpp'}:
        return 'code'
    if 'code' in tokens or 'file' in tokens or 'function' in tokens or 'method' in tokens:
        return 'code'
    if 'skill' in tokens:
        return 'skills'
    return 'general'


def extract_intent(user_text: str) -> dict[str, Any]:
    text = normalize_text(user_text)
    tokens = set(text.split())
    args = extract_args(tokens)
    symbol = extract_symbol_arg(user_text, args)
    if symbol:
        args['symbol'] = symbol
    filetype = extract_filetype(args)
    domain = extract_domain(tokens, filetype)
    action = extract_action(tokens)

    if filetype == 'py':
        tokens.add('python')
    elif filetype in {'js', 'jsx'}:
        tokens.add('javascript')
    elif filetype in {'ts', 'tsx'}:
        tokens.add('typescript')

    return {
        'text': text,
        'tokens': tokens,
        'args': args,
        'action': action,
        'filetype': filetype,
        'domain': domain,
        'speech_act': extract_speech_act(user_text, text),
    }
