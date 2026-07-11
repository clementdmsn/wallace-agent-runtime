from __future__ import annotations

from pydantic import Field

from contracts.base import ContractModel
from contracts.types import JsonValue


class RunTraceEvent(ContractModel):
    ts: str
    event: str = Field(min_length=1)
    run_id: int = Field(ge=0)
    trace_id: str = Field(min_length=1)
    fields: dict[str, JsonValue] = Field(default_factory=dict)

    def to_payload(self) -> dict[str, JsonValue]:
        reserved = {'ts', 'event', 'run_id', 'trace_id'}
        collisions = reserved & self.fields.keys()

        if collisions:
            raise ValueError(f'trace fields contain reserved keys: {sorted(collisions)}')

        return {
            'ts': self.ts,
            'event': self.event,
            'run_id': self.run_id,
            'trace_id': self.trace_id,
            **self.fields,
        }
