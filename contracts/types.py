from __future__ import annotations

from typing_extensions import TypeAliasType


JsonScalar = str | int | float | bool | None
JsonValue = TypeAliasType('JsonValue', JsonScalar | list['JsonValue'] | dict[str, 'JsonValue'])
