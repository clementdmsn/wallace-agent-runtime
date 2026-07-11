from __future__ import annotations

from enum import StrEnum
from typing import cast

from pydantic import BaseModel, ConfigDict

from contracts.types import JsonValue


class ResultStatus(StrEnum):
    OK = 'ok'
    ERROR = 'error'
    APPROVAL_REQUIRED = 'approval_required'


class ContractModel(BaseModel):
    model_config = ConfigDict(extra='forbid', use_enum_values=True, validate_assignment=True)

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], self.model_dump(exclude_none=True, mode='json'))
