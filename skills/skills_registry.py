from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, FrozenSet


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    implementation_name: str
    parameters: dict[str, Any]
    procedure: str = ""
    metadata_path: str = ""
    procedure_path: str = ""
    when_to_use: tuple[str, ...] = field(default_factory=tuple)
    when_not_to_use: tuple[str, ...] = field(default_factory=tuple)
    examples: tuple[str, ...] = field(default_factory=tuple)
    category: str = "general"
    tags: FrozenSet[str] = field(default_factory=frozenset)
    supported_actions: FrozenSet[str] = field(default_factory=frozenset)
    supported_domains: FrozenSet[str] = field(default_factory=frozenset)
    supported_filetypes: FrozenSet[str] = field(default_factory=frozenset)
    required_args: FrozenSet[str] = field(default_factory=frozenset)
    tools_required: tuple[str, ...] = field(default_factory=tuple)
    exclusions: tuple[str, ...] = field(default_factory=tuple)
    preconditions: tuple[str, ...] = field(default_factory=tuple)
    priority: int = 0
    specificity: int = 0
    default_score: float = 0.5
