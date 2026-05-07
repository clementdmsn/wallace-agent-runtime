from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SIDE_EFFECT_HINTS: tuple[tuple[str, str], ...] = (
    ("open", "fs"),
    ("write", "fs"),
    ("unlink", "fs"),
    ("mkdir", "fs"),
    ("requests.", "net"),
    ("httpx.", "net"),
    ("aiohttp.", "net"),
    ("urllib.", "net"),
    ("print", "stdout"),
    ("logging.", "log"),
    ("logger.", "log"),
    ("subprocess.", "proc"),
    ("sqlite", "db"),
    ("session.", "db"),
    ("cursor.", "db"),
)


def short_doc(text: str | None) -> str | None:
    if not text:
        return None
    first = text.strip().split("\n\n", 1)[0].strip()
    return first or None


def top_symbols(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        s for s in symbols
        if s.get("kind") in {"function", "method", "classmethod", "staticmethod"}
        and not s.get("parent_function")
    ]


def get_call_names(symbol: dict[str, Any]) -> list[str]:
    if symbol.get("call_records") and isinstance(symbol["call_records"], list):
        first = symbol["call_records"][0] if symbol["call_records"] else None
        if isinstance(first, dict) and "n" in first:
            return [rec.get("n") for rec in symbol["call_records"] if rec.get("n")]
        if isinstance(first, dict):
            return [rec.get("name") for rec in symbol["call_records"] if rec.get("name")]
    return symbol.get("calls", [])


def get_conditional_calls(symbol: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for rec in symbol.get("call_records", []):
        if rec.get("g"):
            out.append(rec.get("n"))
        elif rec.get("guard"):
            out.append(rec.get("name"))
    return out


def get_writes(symbol: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in symbol.get("writes", []):
        target = item.get("target") if isinstance(item, dict) else None
        if target:
            out.append(target)
    return out


def get_reads(symbol: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in symbol.get("reads", []):
        name = item.get("name") if isinstance(item, dict) else None
        if name:
            out.append(name)
    return out


def get_events(symbol: dict[str, Any]) -> list[dict[str, Any]]:
    return [ev for ev in symbol.get("events", []) if isinstance(ev, dict)]


def classify_side_effects(symbol: dict[str, Any]) -> list[str]:
    hits: set[str] = set()
    for name in get_call_names(symbol):
        for needle, label in SIDE_EFFECT_HINTS:
            if needle in name:
                hits.add(label)
    for target in get_writes(symbol):
        if "." in target or "[" in target:
            hits.add("mut")
    for name in get_reads(symbol):
        if name.startswith("os.environ") or name.startswith("os.getenv"):
            hits.add("env")
    return sorted(hits)


def compute_risks(symbol: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    events = get_events(symbol)
    if any(rec.get("a") or rec.get("awaited") for rec in symbol.get("call_records", [])):
        risks.append("async")
    if any((ev.get("t") == "except" and ev.get("x") == "Exception") or (ev.get("type") == "except" and ev.get("exception") == "Exception") for ev in events):
        risks.append("broad_except")
    if symbol.get("nested_symbols"):
        risks.append("nested_defs")
    if len(get_writes(symbol)) > 3:
        risks.append("stateful")
    guard_count = sum(1 for ev in events if ev.get("t") == "guard" or ev.get("type") == "guard")
    if guard_count > 3:
        risks.append("branchy")
    return risks


def execution_outline(symbol: dict[str, Any], limit: int) -> list[str]:
    lines: list[str] = []
    for ev in get_events(symbol)[:limit]:
        t = ev.get("t") or ev.get("type")
        if t == "guard":
            lines.append(f"if {ev.get('x') or ev.get('expr')}")
        elif t == "call":
            awaited = ev.get("a") or ev.get("awaited")
            name = ev.get("n") or ev.get("name")
            lines.append(("await " if awaited else "call ") + str(name))
        elif t == "assign":
            x = ev.get("x") or ev.get("targets") or []
            if isinstance(x, list):
                lines.append("set " + ", ".join(map(str, x[:2])))
        elif t == "return":
            lines.append("return " + str(ev.get("x") or ev.get("expr")))
        elif t == "raise":
            lines.append("raise " + str(ev.get("x") or ev.get("expr")))
        elif t == "loop":
            lines.append("loop")
        elif t == "except":
            lines.append("except " + str(ev.get("x") or ev.get("exception")))
    return lines


def build_symbol_summary(symbol: dict[str, Any], compact: bool, outline_limit: int) -> dict[str, Any]:
    calls = get_call_names(symbol)
    conditional = get_conditional_calls(symbol)
    writes = get_writes(symbol)
    returns = symbol.get("returns", [])[:3]
    raises = symbol.get("raises", [])[:3]
    summary: dict[str, Any]
    if compact:
        summary = {
            "q": symbol.get("qualified_name"),
            "k": symbol.get("kind"),
            "l": [symbol.get("lineno"), symbol.get("end_lineno")],
            "p": symbol.get("params", []),
            "c": calls[:8],
            "cc": conditional[:5],
            "w": writes[:6],
            "r": returns,
            "x": raises,
            "fx": classify_side_effects(symbol),
            "risk": compute_risks(symbol),
            "ol": execution_outline(symbol, outline_limit),
        }
        doc = short_doc(symbol.get("docstring"))
        if doc:
            summary["d"] = doc
    else:
        summary = {
            "qualified_name": symbol.get("qualified_name"),
            "kind": symbol.get("kind"),
            "lines": [symbol.get("lineno"), symbol.get("end_lineno")],
            "doc": short_doc(symbol.get("docstring")),
            "params": symbol.get("params", []),
            "top_calls": calls[:8],
            "conditional_calls": conditional[:5],
            "writes": writes[:6],
            "returns": returns,
            "raises": raises,
            "side_effects": classify_side_effects(symbol),
            "risk_areas": compute_risks(symbol),
            "execution_outline": execution_outline(symbol, outline_limit),
        }
    return summary


def module_summary(doc: dict[str, Any], compact: bool, outline_limit: int) -> dict[str, Any]:
    symbols = top_symbols(doc.get("symbols", []))
    imports = [imp.get("module") for imp in doc.get("imports", []) if imp.get("module")]
    symbol_summaries = [build_symbol_summary(sym, compact=compact, outline_limit=outline_limit) for sym in symbols]
    all_effects = sorted({e for sym in symbol_summaries for e in (sym.get("fx") if compact else sym.get("side_effects", []))})
    all_risks = sorted({r for sym in symbol_summaries for r in (sym.get("risk") if compact else sym.get("risk_areas", []))})
    if compact:
        out = {
            "m": doc.get("module"),
            "ep": [s.get("q") for s in symbol_summaries[:12]],
            "dep": sorted(set(imports))[:20],
            "fx": all_effects,
            "risk": all_risks,
            "sym": symbol_summaries,
        }
        module_doc = short_doc(doc.get("module_docstring"))
        if module_doc:
            out["d"] = module_doc
        return out
    return {
        "module": doc.get("module"),
        "module_doc": short_doc(doc.get("module_docstring")),
        "entry_points": [s.get("qualified_name") for s in symbol_summaries[:12]],
        "external_dependencies": sorted(set(imports))[:20],
        "module_side_effects": all_effects,
        "module_risk_areas": all_risks,
        "symbols": symbol_summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Project code IR into a compact understanding summary.")
    parser.add_argument("symbols_json", help="Path to JSON emitted by code_to_sym.py")
    parser.add_argument("--compact", action="store_true", help="Emit shorter key names and compact JSON")
    parser.add_argument("--outline-limit", type=int, default=8)
    args = parser.parse_args()

    data = json.loads(Path(args.symbols_json).read_text(encoding="utf-8"))
    result = module_summary(data, compact=args.compact, outline_limit=args.outline_limit)
    if args.compact:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
