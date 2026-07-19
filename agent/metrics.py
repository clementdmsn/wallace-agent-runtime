from __future__ import annotations

import time
from copy import deepcopy
from typing import Any


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def elapsed_ms(start_ms: float) -> float:
    return round(now_ms() - start_ms, 2)


def estimate_messages_chars(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        total += len(str(message.get('role', '')))
        content = message.get('content')
        if content is not None:
            total += len(str(content))
        if message.get('tool_calls'):
            total += len(str(message.get('tool_calls')))
    return total


class AgentMetrics:
    def __init__(self, history_limit: int = 20):
        self.history_limit = history_limit
        self.current_request: dict[str, Any] | None = None
        self.history: list[dict[str, Any]] = []
        self.baseline: dict[str, Any] | None = None

    def reset_current(self) -> None:
        self.current_request = None

    def start_request(self, run_id: int, model: str, system_prompt_chars: int) -> None:
        self.current_request = {
            'id': run_id,
            'model': model,
            'started_ms': now_ms(),
            'finished_ms': None,
            'request_total_ms': None,
            'auto_turns': 0,
            'tool_call_count': 0,
            'estimated_prompt_chars': 0,
            'estimated_system_prompt_chars': system_prompt_chars,
            'uncompacted_prompt_chars': 0,
            'context_reference_saved_chars': 0,
            'context_reference_count': 0,
            'model_calls': [],
            'tool_calls': [],
        }

    def finish_request(self, run_id: int) -> None:
        request = self.current_request
        if not request or request.get('id') != run_id:
            return

        request['finished_ms'] = now_ms()
        request['request_total_ms'] = round(request['finished_ms'] - request['started_ms'], 2)
        self.history.append(deepcopy(request))
        self.history = self.history[-self.history_limit:]

    def start_model_call(
        self,
        run_id: int,
        turn: int,
        model: str,
        prompt_chars: int,
        *,
        uncompacted_prompt_chars: int | None = None,
        compaction_stats: dict[str, Any] | None = None,
    ) -> int | None:
        request = self.current_request
        if not request or request.get('id') != run_id:
            return None

        uncompacted = prompt_chars if uncompacted_prompt_chars is None else uncompacted_prompt_chars
        stats = compaction_stats or {}
        call = {
            'turn': turn,
            'model': model,
            'started_ms': now_ms(),
            'finished_ms': None,
            'ttft_ms': None,
            'first_output_kind': None,
            'model_total_ms': None,
            'prompt_chars': prompt_chars,
            'uncompacted_prompt_chars': uncompacted,
            'context_reference_saved_chars': int(stats.get('context_reference_saved_chars') or 0),
            'context_reference_count': int(stats.get('context_reference_count') or 0),
        }
        request['model_calls'].append(call)
        request['auto_turns'] = max(int(request.get('auto_turns', 0)), turn + 1)
        request['estimated_prompt_chars'] += prompt_chars
        request['uncompacted_prompt_chars'] += uncompacted
        request['context_reference_saved_chars'] += call['context_reference_saved_chars']
        request['context_reference_count'] += call['context_reference_count']
        return len(request['model_calls']) - 1

    def mark_first_output(self, run_id: int, call_index: int | None, kind: str) -> None:
        call = self._model_call(run_id, call_index)
        if not call or call.get('ttft_ms') is not None:
            return
        call['ttft_ms'] = elapsed_ms(float(call['started_ms']))
        call['first_output_kind'] = kind

    def finish_model_call(self, run_id: int, call_index: int | None) -> None:
        call = self._model_call(run_id, call_index)
        if not call:
            return
        call['finished_ms'] = now_ms()
        call['model_total_ms'] = round(call['finished_ms'] - call['started_ms'], 2)

    def record_tool_call(self, run_id: int, tool: str, status: str, duration_ms: float) -> None:
        request = self.current_request
        if not request or request.get('id') != run_id:
            return

        request['tool_call_count'] += 1
        request['tool_calls'].append({
            'tool': tool,
            'status': status,
            'duration_ms': round(duration_ms, 2),
        })

    def set_baseline(self, baseline: dict[str, Any]) -> None:
        self.baseline = deepcopy(baseline)

    def snapshot(self) -> dict[str, Any]:
        current = deepcopy(self.current_request)
        if current and current.get('request_total_ms') is None:
            current['request_elapsed_ms'] = round(now_ms() - current['started_ms'], 2)
            for call in current.get('model_calls') or []:
                if call.get('model_total_ms') is None:
                    call['model_elapsed_ms'] = round(now_ms() - call['started_ms'], 2)

        return {
            'current_request': current,
            'last_request': deepcopy(self.history[-1]) if self.history else None,
            'history': deepcopy(self.history[-5:]),
            'baseline': deepcopy(self.baseline),
        }

    def _model_call(self, run_id: int, call_index: int | None) -> dict[str, Any] | None:
        request = self.current_request
        if not request or request.get('id') != run_id or call_index is None:
            return None
        calls = request.get('model_calls') or []
        if call_index < 0 or call_index >= len(calls):
            return None
        return calls[call_index]
