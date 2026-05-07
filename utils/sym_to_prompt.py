from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def top_symbols(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        s for s in doc.get("symbols", [])
        if s.get("kind") in {"function", "method", "classmethod", "staticmethod"}
        and not s.get("parent_function")
    ]


def prompt_projection(doc: dict[str, Any], max_symbols: int, max_calls: int, max_events: int) -> dict[str, Any]:
    out_symbols: list[dict[str, Any]] = []
    for sym in top_symbols(doc)[:max_symbols]:
        calls: list[str] = []
        for rec in sym.get("call_records", []):
            if isinstance(rec, dict):
                name = rec.get("n") or rec.get("name")
                if name:
                    calls.append(name)
        if not calls:
            calls = sym.get("calls", [])

        events: list[str] = []
        for ev in sym.get("events", [])[:max_events]:
            if not isinstance(ev, dict):
                continue
            t = ev.get("t") or ev.get("type")
            if t == "call":
                events.append(f"call:{ev.get('n') or ev.get('name')}")
            elif t == "return":
                events.append(f"return:{ev.get('x') or ev.get('expr')}")
            elif t == "raise":
                events.append(f"raise:{ev.get('x') or ev.get('expr')}")
            elif t == "guard":
                events.append(f"guard:{ev.get('x') or ev.get('expr')}")
            elif t == "assign":
                xs = ev.get("x") or ev.get("targets") or []
                if xs:
                    events.append("assign:" + ",".join(xs[:2]))

        out_symbols.append({
            "q": sym.get("qualified_name"),
            "k": sym.get("kind"),
            "l": [sym.get("lineno"), sym.get("end_lineno")],
            "p": sym.get("params", []),
            "c": calls[:max_calls],
            "w": [w.get("target") for w in sym.get("writes", [])[:5] if isinstance(w, dict) and w.get("target")],
            "r": sym.get("returns", [])[:3],
            "x": sym.get("raises", [])[:3],
            "e": events,
        })

    return {
        "m": doc.get("module"),
        "sym": out_symbols,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Project code IR into a minimal prompt-friendly schema.")
    parser.add_argument("symbols_json")
    parser.add_argument("--max-symbols", type=int, default=6)
    parser.add_argument("--max-calls", type=int, default=6)
    parser.add_argument("--max-events", type=int, default=6)
    args = parser.parse_args()

    data = json.loads(Path(args.symbols_json).read_text(encoding="utf-8"))
    print(json.dumps(prompt_projection(data, args.max_symbols, args.max_calls, args.max_events), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
