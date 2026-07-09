from pydantic import Field
from typing import Any

from contracts.base import ContractModel

class ToolEvent(ContractModel): 
    id: str = ''
    kind: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: Any | None = None
    tool: str | None = None
    status: str | None = None
    error: str | None = None
    message: str | None = None
    skill_name: str | None = None

