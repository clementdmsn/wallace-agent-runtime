from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedToolCall:
    call_id: str
    name: str
    raw_args: str


def reject_json_constant(value: str) -> None:
    raise ValueError(f'invalid JSON constant: {value}')


def parse_tool_call(tool_call: dict[str, Any]) -> ParsedToolCall:
    function = tool_call.get('function') or {}
    return ParsedToolCall(
        call_id=str(tool_call.get('id', '')),
        name=str(function.get('name', '')),
        raw_args=function.get('arguments', '{}') or '{}',
    )


def parse_tool_args(raw_args: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        args = json.loads(raw_args, parse_constant=reject_json_constant)
        if not isinstance(args, dict):
            raise ValueError('call arguments must decode to an object')
    except Exception as exc:
        return None, {'status': 'error', 'error': f'invalid call arguments: {exc}'}
    return args, None
