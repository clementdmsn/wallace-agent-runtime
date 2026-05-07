from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def md_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("*", "\\*")
        .replace("_", "\\_")
    )


def render_inline_list(items: list[str], limit: int | None = None) -> list[str]:
    if not items:
        return ["- None"]
    if limit is not None:
        items = items[:limit]
    return [f"- `{md_escape(item)}`" for item in items]


def render_text_list(items: list[str], limit: int | None = None) -> list[str]:
    if not items:
        return ["- None"]
    if limit is not None:
        items = items[:limit]
    return [f"- {md_escape(item)}" for item in items]


def short_doc(text: str | None) -> str | None:
    if not text:
        return None
    first = text.strip().split("\n\n", 1)[0].strip()
    return first or None


def simplify_records(items: list[Any], key: str) -> list[str]:
    out: list[str] = []
    for item in items:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            value = item.get(key)
            if isinstance(value, str):
                out.append(value)
    return out


def collect_instance_attributes(methods: list[dict[str, Any]]) -> list[str]:
    attrs: list[str] = []
    for method in methods:
        attrs.extend(method.get('instance_attributes', []))
        attrs.extend(simplify_records(method.get('writes', []), 'target'))
    attrs = [a for a in attrs if a.startswith('self.')]
    deduped: list[str] = []
    seen: set[str] = set()
    for attr in attrs:
        if attr not in seen:
            seen.add(attr)
            deduped.append(attr)
    return deduped


def group_symbols(symbols: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    classes = [s for s in symbols if s["kind"] == "class"]
    module_functions = [s for s in symbols if s["kind"] == "function"]
    methods_by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for sym in symbols:
        if sym["kind"] in {"method", "classmethod", "staticmethod"}:
            class_name = sym.get("class_name")
            if class_name:
                methods_by_class[class_name].append(sym)

    classes.sort(key=lambda x: x["name"])
    module_functions.sort(key=lambda x: x["name"])
    for class_name in methods_by_class:
        methods_by_class[class_name].sort(key=lambda x: x["name"])

    return classes, methods_by_class, module_functions


def render_function(symbol: dict[str, Any], heading: str = "###") -> list[str]:
    lines: list[str] = []

    title = symbol.get("qualified_name") or symbol["name"]
    lines.append(f"{heading} `{md_escape(title)}`")
    lines.append("")

    kind = symbol["kind"]
    if symbol.get("is_async"):
        kind = f"async {kind}"
    lines.append(f"**Type:** `{md_escape(kind)}`  ")
    lines.append(f"**Lines:** `{symbol['lineno']}-{symbol['end_lineno']}`")
    lines.append("")

    doc = short_doc(symbol.get("docstring"))
    if doc:
        lines.append(doc)
        lines.append("")

    params = symbol.get("params", [])
    lines.append("**Parameters**")
    lines.append("")
    lines.extend(render_inline_list(params))
    lines.append("")

    decorators = symbol.get("decorators", [])
    if decorators:
        lines.append("**Decorators**")
        lines.append("")
        lines.extend(render_inline_list(decorators))
        lines.append("")

    instance_attrs = symbol.get("instance_attributes", [])
    if instance_attrs:
        lines.append("**Instance attributes assigned**")
        lines.append("")
        lines.extend(render_inline_list(instance_attrs))
        lines.append("")

    calls = symbol.get("calls", [])
    lines.append("**Calls**")
    lines.append("")
    lines.extend(render_inline_list(calls))
    lines.append("")

    returns = symbol.get("returns", [])
    lines.append("**Returns**")
    lines.append("")
    lines.extend(render_inline_list(returns))
    lines.append("")

    raises = symbol.get("raises", [])
    lines.append("**Raises**")
    lines.append("")
    lines.extend(render_inline_list(raises))
    lines.append("")

    reads = simplify_records(symbol.get("reads", []), "name")
    if reads:
        lines.append("**Reads**")
        lines.append("")
        lines.extend(render_inline_list(reads))
        lines.append("")

    writes = simplify_records(symbol.get("writes", []), "target")
    if writes:
        lines.append("**Writes**")
        lines.append("")
        lines.extend(render_inline_list(writes))
        lines.append("")

    nested = symbol.get("nested_symbols", [])
    nested_names = [n.get("qualified_name") or n.get("name", "<nested>") for n in nested if isinstance(n, dict)]
    if nested_names:
        lines.append("**Nested symbols**")
        lines.append("")
        lines.extend(render_inline_list(nested_names))
        lines.append("")

    return lines


def render_class(symbol: dict[str, Any], methods: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    lines.append(f"## Class `{md_escape(symbol['name'])}`")
    lines.append("")

    lines.append(f"**Lines:** `{symbol['lineno']}-{symbol['end_lineno']}`")
    lines.append("")

    bases = symbol.get("bases", [])
    if bases:
        lines.append("**Bases**")
        lines.append("")
        lines.extend(render_inline_list(bases))
        lines.append("")

    class_attrs = symbol.get("attributes", [])
    if class_attrs:
        lines.append("**Class attributes**")
        lines.append("")
        lines.extend(render_inline_list(class_attrs))
        lines.append("")

    instance_attrs = collect_instance_attributes(methods)
    if instance_attrs:
        lines.append("**Instance attributes**")
        lines.append("")
        lines.extend(render_inline_list(instance_attrs))
        lines.append("")

    doc = short_doc(symbol.get("docstring"))
    if doc:
        lines.append(doc)
        lines.append("")

    if methods:
        lines.append("### Method list")
        lines.append("")
        for method in methods:
            kind = method["kind"]
            if method.get("is_async"):
                kind = f"async {kind}"
            lines.append(
                f"- `{md_escape(method.get('qualified_name') or method['name'])}` "
                f"({md_escape(kind)}) "
                f"`{method['lineno']}-{method['end_lineno']}`"
            )
        lines.append("")

        lines.append("### Methods")
        lines.append("")
        for i, method in enumerate(methods):
            lines.extend(render_function(method, heading="####"))
            if i < len(methods) - 1:
                lines.append("---")
                lines.append("")

    return lines


def render_markdown(doc: dict[str, Any]) -> str:
    module = doc.get("module", "module")
    symbols = doc.get("symbols", [])

    classes, methods_by_class, module_functions = group_symbols(symbols)

    lines: list[str] = []
    lines.append(f"# `{md_escape(module)}`")
    lines.append("")
    lines.append("Readable reference generated from code symbols.")
    lines.append("")

    if module_functions:
        lines.append("## Module functions")
        lines.append("")
        for i, fn in enumerate(module_functions):
            lines.extend(render_function(fn))
            if i < len(module_functions) - 1:
                lines.append("---")
                lines.append("")

    if classes:
        if module_functions:
            lines.append("")
        for i, cls in enumerate(classes):
            lines.extend(render_class(cls, methods_by_class.get(cls["name"], [])))
            if i < len(classes) - 1:
                lines.append("")
                lines.append("---")
                lines.append("")

    if not classes and not module_functions:
        lines.append("_No documented symbols found._")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python sym_to_md.py <symbols.json>", file=sys.stderr)
        return 1

    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    print(render_markdown(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
