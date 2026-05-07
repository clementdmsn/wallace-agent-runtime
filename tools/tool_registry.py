from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Tool:
    name: str
    func: Callable[..., Any]
