from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


MODE_INDEX = "index"
MODE_SUMMARY = "summary"
MODE_DETAILED = "detailed"
VALID_MODES = {MODE_INDEX, MODE_SUMMARY, MODE_DETAILED}


IMPORTANT_READ_PREFIXES = (
    "os.environ",
    "os.getenv",
    "settings",
    "config",
    "env",
    "self.",
)


CONTEXT_LOOP = "loop"
CONTEXT_TRY = "try"
CONTEXT_EXCEPT = "except"
CONTEXT_WITH = "with"


def safe_unparse(node: ast.AST | None, default: str = "<expression>") -> str:
    if node is None:
        return default
    try:
        return ast.unparse(node)
    except Exception:
        return default


def get_call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        current: ast.AST | None = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
    return None


def is_docstring_stmt(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def collect_params(args: ast.arguments) -> list[str]:
    params: list[str] = []
    for arg in getattr(args, "posonlyargs", []):
        params.append(arg.arg)
    for arg in args.args:
        params.append(arg.arg)
    if args.vararg:
        params.append(f"*{args.vararg.arg}")
    for arg in args.kwonlyargs:
        params.append(arg.arg)
    if args.kwarg:
        params.append(f"**{args.kwarg.arg}")
    return params


def collect_assignment_targets(node: ast.AST) -> list[str]:
    targets: list[str] = []

    def collect(target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            targets.append(target.id)
        elif isinstance(target, ast.Attribute):
            targets.append(safe_unparse(target))
        elif isinstance(target, ast.Subscript):
            targets.append(safe_unparse(target))
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                collect(elt)

    if isinstance(node, ast.Assign):
        for t in node.targets:
            collect(t)
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        collect(node.target)

    return targets


def collect_class_attributes(node: ast.ClassDef) -> list[str]:
    attrs: list[str] = []
    for stmt in node.body:
        if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            attrs.extend(name for name in collect_assignment_targets(stmt) if not name.startswith('self.'))
    return unique_preserve(attrs)


def collect_instance_attributes_from_writes(writes: list[dict[str, Any]]) -> list[str]:
    return unique_preserve([w.get('target') for w in writes if isinstance(w.get('target'), str) and w.get('target', '').startswith('self.')])


class FunctionBodyAnalyzer(ast.NodeVisitor):
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.call_records: list[dict[str, Any]] = []
        self.reads: list[dict[str, Any]] = []
        self.writes: list[dict[str, Any]] = []
        self.return_records: list[dict[str, Any]] = []
        self.raise_records: list[dict[str, Any]] = []
        self.nested_symbols: list[dict[str, Any]] = []

        self._guards: list[str] = []
        self._contexts: list[str] = []
        self._call_stack: list[str] = []
        self._event_index = 0
        self._seen_call_keys: set[tuple[Any, ...]] = set()
        self._seen_read_keys: set[tuple[Any, ...]] = set()
        self._seen_write_keys: set[tuple[Any, ...]] = set()

    def current_guard(self) -> str | None:
        return " and ".join(self._guards) if self._guards else None

    def current_contexts(self) -> list[str]:
        return list(self._contexts)

    def _append_event(self, event: dict[str, Any]) -> None:
        event = dict(event)
        event.setdefault("index", self._event_index)
        if "guard" not in event:
            event["guard"] = self.current_guard()
        if "contexts" not in event:
            event["contexts"] = self.current_contexts()
        self.events.append(event)
        self._event_index += 1

    def _record_read(self, name: str, lineno: int | None) -> None:
        if not name:
            return
        key = (name, lineno)
        if key in self._seen_read_keys:
            return
        self._seen_read_keys.add(key)
        self.reads.append({"name": name, "lineno": lineno})

    def _record_write(self, target: str, lineno: int | None) -> None:
        if not target:
            return
        key = (target, lineno)
        if key in self._seen_write_keys:
            return
        self._seen_write_keys.add(key)
        self.writes.append({"target": target, "lineno": lineno})

    def _record_call(self, call_node: ast.Call, awaited: bool = False) -> None:
        name = get_call_name(call_node.func) or safe_unparse(call_node.func)
        parent_call = self._call_stack[-1] if self._call_stack else None
        key = (name, getattr(call_node, "lineno", None), self.current_guard(), tuple(self.current_contexts()), awaited, parent_call)
        if key in self._seen_call_keys:
            return
        self._seen_call_keys.add(key)
        record = {
            "name": name,
            "lineno": getattr(call_node, "lineno", None),
            "guard": self.current_guard(),
            "contexts": self.current_contexts(),
            "awaited": awaited,
            "parent_call": parent_call,
            "nesting_depth": len(self._call_stack),
        }
        self.call_records.append(record)
        self._append_event({
            "type": "call",
            "name": name,
            "lineno": getattr(call_node, "lineno", None),
            "awaited": awaited,
            "parent_call": parent_call,
            "nesting_depth": len(self._call_stack),
        })

    def _record_nested_symbol(self, node: ast.AST, kind: str) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self.nested_symbols.append({
                "kind": kind,
                "name": node.name,
                "qualified_name": node.name,
                "lineno": getattr(node, "lineno", None),
                "end_lineno": getattr(node, "end_lineno", getattr(node, "lineno", None)),
            })

    def visit_If(self, node: ast.If) -> Any:
        test = safe_unparse(node.test)
        self._append_event({"type": "guard", "expr": f"if {test}", "lineno": node.lineno})
        self._guards.append(test)
        for stmt in node.body:
            self.visit(stmt)
        self._guards.pop()

        if node.orelse:
            negated = f"not ({test})"
            self._append_event({"type": "guard", "expr": f"else for {test}", "lineno": node.lineno})
            self._guards.append(negated)
            for stmt in node.orelse:
                self.visit(stmt)
            self._guards.pop()
        return None

    def visit_For(self, node: ast.For) -> Any:
        self._append_event({"type": "loop", "kind": "for", "lineno": node.lineno, "target": safe_unparse(node.target), "iterable": safe_unparse(node.iter)})
        self._contexts.append(CONTEXT_LOOP)
        self.visit(node.target)
        self.visit(node.iter)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)
        self._contexts.pop()
        return None

    def visit_AsyncFor(self, node: ast.AsyncFor) -> Any:
        return self.visit_For(node)

    def visit_While(self, node: ast.While) -> Any:
        test = safe_unparse(node.test)
        self._append_event({"type": "loop", "kind": "while", "lineno": node.lineno, "test": test})
        self._contexts.append(CONTEXT_LOOP)
        self._guards.append(test)
        for stmt in node.body:
            self.visit(stmt)
        self._guards.pop()
        for stmt in node.orelse:
            self.visit(stmt)
        self._contexts.pop()
        return None

    def visit_Try(self, node: ast.Try) -> Any:
        self._contexts.append(CONTEXT_TRY)
        for stmt in node.body:
            self.visit(stmt)
        self._contexts.pop()
        for handler in node.handlers:
            exc = safe_unparse(handler.type, "Exception") if handler.type else "Exception"
            self._append_event({"type": "except", "exception": exc, "lineno": handler.lineno})
            self._contexts.append(CONTEXT_EXCEPT)
            for stmt in handler.body:
                self.visit(stmt)
            self._contexts.pop()
        for stmt in node.orelse:
            self.visit(stmt)
        for stmt in node.finalbody:
            self.visit(stmt)
        return None

    def visit_With(self, node: ast.With) -> Any:
        items = [safe_unparse(item.context_expr) for item in node.items]
        self._append_event({"type": "with", "items": items, "lineno": node.lineno})
        self._contexts.append(CONTEXT_WITH)
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self.visit(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)
        self._contexts.pop()
        return None

    def visit_AsyncWith(self, node: ast.AsyncWith) -> Any:
        return self.visit_With(node)

    def visit_Assign(self, node: ast.Assign) -> Any:
        targets = [safe_unparse(t) for t in node.targets]
        for target in targets:
            self._record_write(target, node.lineno)
        self._append_event({"type": "assign", "targets": targets, "lineno": node.lineno})
        for target in node.targets:
            self.visit(target)
        self.visit(node.value)
        return None

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        target = safe_unparse(node.target)
        self._record_write(target, node.lineno)
        self._append_event({"type": "assign", "targets": [target], "lineno": node.lineno})
        self.visit(node.target)
        if node.value is not None:
            self.visit(node.value)
        return None

    def visit_AugAssign(self, node: ast.AugAssign) -> Any:
        target = safe_unparse(node.target)
        self._record_write(target, node.lineno)
        self._append_event({"type": "assign", "targets": [target], "lineno": node.lineno})
        self.visit(node.target)
        self.visit(node.value)
        return None

    def visit_Return(self, node: ast.Return) -> Any:
        expr = safe_unparse(node.value, "None") if node.value is not None else "None"
        record = {"expr": expr, "lineno": node.lineno, "guard": self.current_guard()}
        self.return_records.append(record)
        self._append_event({"type": "return", "expr": expr, "lineno": node.lineno})
        if node.value is not None:
            self.visit(node.value)
        return None

    def visit_Raise(self, node: ast.Raise) -> Any:
        expr = safe_unparse(node.exc, "<re-raise>")
        record = {"expr": expr, "lineno": node.lineno, "guard": self.current_guard()}
        self.raise_records.append(record)
        self._append_event({"type": "raise", "expr": expr, "lineno": node.lineno})
        if node.exc is not None:
            self.visit(node.exc)
        return None

    def visit_Await(self, node: ast.Await) -> Any:
        if isinstance(node.value, ast.Call):
            self._record_call(node.value, awaited=True)
            name = get_call_name(node.value.func) or safe_unparse(node.value.func)
            self._call_stack.append(name)
            self.visit(node.value.func)
            for arg in node.value.args:
                self.visit(arg)
            for kw in node.value.keywords:
                self.visit(kw.value)
            self._call_stack.pop()
        else:
            self.visit(node.value)
        return None

    def visit_Call(self, node: ast.Call) -> Any:
        self._record_call(node, awaited=False)
        name = get_call_name(node.func) or safe_unparse(node.func)
        self._call_stack.append(name)
        self.visit(node.func)
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw.value)
        self._call_stack.pop()
        return None

    def visit_Name(self, node: ast.Name) -> Any:
        if isinstance(node.ctx, ast.Load):
            self._record_read(node.id, getattr(node, "lineno", None))
        elif isinstance(node.ctx, ast.Store):
            self._record_write(node.id, getattr(node, "lineno", None))
        return None

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        name = safe_unparse(node)
        if isinstance(node.ctx, ast.Load):
            self._record_read(name, getattr(node, "lineno", None))
        elif isinstance(node.ctx, ast.Store):
            self._record_write(name, getattr(node, "lineno", None))
        self.visit(node.value)
        return None

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        name = safe_unparse(node)
        if isinstance(node.ctx, ast.Load):
            self._record_read(name, getattr(node, "lineno", None))
        elif isinstance(node.ctx, ast.Store):
            self._record_write(name, getattr(node, "lineno", None))
        self.visit(node.value)
        self.visit(node.slice)
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._record_nested_symbol(node, "nested_function")
        return None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._record_nested_symbol(node, "nested_async_function")
        return None

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self._record_nested_symbol(node, "nested_class")
        return None


class SymbolExtractor(ast.NodeVisitor):
    def __init__(self, module_name: str, mode: str = MODE_SUMMARY) -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"invalid mode: {mode}")
        self.module_name = module_name
        self.mode = mode
        self.class_stack: list[str] = []
        self.function_stack: list[str] = []
        self.symbols: list[dict[str, Any]] = []
        self.imports: list[dict[str, Any]] = []
        self.module_docstring: str | None = None

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            self.imports.append({
                "module": alias.name,
                "alias": alias.asname,
                "lineno": node.lineno,
            })
        return None

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        module = node.module or ""
        for alias in node.names:
            full = f"{module}.{alias.name}" if module else alias.name
            self.imports.append({
                "module": full,
                "alias": alias.asname,
                "lineno": node.lineno,
            })
        return None

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        bases = [safe_unparse(base) for base in node.bases]
        qualified_name = ".".join(self.class_stack + [node.name])
        self.symbols.append({
            "kind": "class",
            "module": self.module_name,
            "name": node.name,
            "qualified_name": qualified_name,
            "bases": bases,
            "attributes": collect_class_attributes(node),
            "docstring": ast.get_docstring(node),
            "lineno": node.lineno,
            "end_lineno": getattr(node, "end_lineno", node.lineno),
            **({"nested_symbols": []} if self.mode == MODE_DETAILED else {}),
        })
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._handle_function(node, is_async=False)
        return None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._handle_function(node, is_async=True)
        return None

    def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        decorators = [safe_unparse(dec) for dec in node.decorator_list]
        params = collect_params(node.args)
        class_name = self.class_stack[-1] if self.class_stack else None
        parent_function = self.function_stack[-1] if self.function_stack else None

        base_name = node.name
        if class_name is None and parent_function is None:
            qualified_name = base_name
        elif class_name is not None and parent_function is None:
            qualified_name = f"{class_name}.{base_name}"
        elif class_name is None and parent_function is not None:
            qualified_name = f"{parent_function}.{base_name}"
        else:
            qualified_name = f"{parent_function}.{base_name}"

        if parent_function is not None:
            kind = "nested_async_function" if is_async else "nested_function"
        elif class_name is None:
            kind = "function"
        elif any(dec.endswith("classmethod") or dec == "classmethod" for dec in decorators):
            kind = "classmethod"
        elif any(dec.endswith("staticmethod") or dec == "staticmethod" for dec in decorators):
            kind = "staticmethod"
        else:
            kind = "method"

        symbol: dict[str, Any] = {
            "kind": kind,
            "module": self.module_name,
            "class_name": class_name,
            "parent_function": parent_function,
            "name": node.name,
            "qualified_name": qualified_name,
            "is_async": is_async,
            "params": params,
            "decorators": decorators,
            "docstring": ast.get_docstring(node),
            "lineno": node.lineno,
            "end_lineno": getattr(node, "end_lineno", node.lineno),
        }

        if self.mode != MODE_INDEX:
            body_analyzer = FunctionBodyAnalyzer()
            self.function_stack.append(qualified_name)
            try:
                for stmt in node.body:
                    if is_docstring_stmt(stmt):
                        continue
                    body_analyzer.visit(stmt)
            finally:
                self.function_stack.pop()

            symbol["calls"] = unique_preserve([rec["name"] for rec in body_analyzer.call_records])
            symbol["returns"] = unique_preserve([rec["expr"] for rec in body_analyzer.return_records])
            symbol["raises"] = unique_preserve([rec["expr"] for rec in body_analyzer.raise_records])
            symbol["instance_attributes"] = collect_instance_attributes_from_writes(body_analyzer.writes)

            if self.mode == MODE_SUMMARY:
                symbol["reads"] = compress_reads(body_analyzer.reads)
                symbol["writes"] = body_analyzer.writes[:10]
                symbol["nested_symbols"] = body_analyzer.nested_symbols[:8]
                symbol["call_records"] = compress_call_records(body_analyzer.call_records)
                symbol["events"] = compress_events(body_analyzer.events)
            else:
                symbol["reads"] = body_analyzer.reads
                symbol["writes"] = body_analyzer.writes
                symbol["nested_symbols"] = body_analyzer.nested_symbols
                symbol["call_records"] = body_analyzer.call_records
                symbol["events"] = body_analyzer.events
                symbol["return_records"] = body_analyzer.return_records
                symbol["raise_records"] = body_analyzer.raise_records

        self.symbols.append(symbol)

    def extract(self, tree: ast.Module) -> dict[str, Any]:
        self.module_docstring = ast.get_docstring(tree)
        self.visit(tree)
        result: dict[str, Any] = {
            "module": self.module_name,
            "module_docstring": self.module_docstring,
            "imports": self.imports,
            "symbols": self.symbols,
            "mode": self.mode,
        }
        return result


def unique_preserve(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def compress_call_records(records: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in records[:limit]:
        item = {"n": rec.get("name"), "l": rec.get("lineno")}
        if rec.get("guard"):
            item["g"] = rec.get("guard")
        if rec.get("awaited"):
            item["a"] = 1
        if rec.get("parent_call"):
            item["p"] = rec.get("parent_call")
        if rec.get("contexts"):
            item["c"] = rec.get("contexts")
        out.append(item)
    return out


def compress_events(events: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in events[:limit]:
        kind = ev.get("type")
        item: dict[str, Any] = {"t": kind, "l": ev.get("lineno")}
        if kind == "call":
            item["n"] = ev.get("name")
            if ev.get("awaited"):
                item["a"] = 1
            if ev.get("guard"):
                item["g"] = ev.get("guard")
        elif kind == "assign":
            item["x"] = ev.get("targets", [])[:3]
        elif kind in {"return", "raise", "guard"}:
            item["x"] = ev.get("expr")
        elif kind == "loop":
            item["x"] = ev.get("iterable") or ev.get("test")
        elif kind == "except":
            item["x"] = ev.get("exception")
        elif kind == "with":
            item["x"] = ev.get("items", [])[:2]
        out.append(item)
    return out


def compress_reads(reads: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    important = [r for r in reads if any(r.get("name", "").startswith(prefix) for prefix in IMPORTANT_READ_PREFIXES)]
    chosen = important or reads[:limit]
    return chosen[:limit]


def extract_symbols_from_code(code: str, module_name: str, mode: str = MODE_SUMMARY) -> dict[str, Any]:
    tree = ast.parse(code)
    extractor = SymbolExtractor(module_name=module_name, mode=mode)
    return extractor.extract(tree)


def extract_symbols_from_file(path: str | Path, mode: str = MODE_SUMMARY) -> dict[str, Any]:
    path = Path(path)
    code = path.read_text(encoding="utf-8")
    return extract_symbols_from_code(code, module_name=path.name, mode=mode)


def filter_symbols(doc: dict[str, Any], selected: set[str]) -> dict[str, Any]:
    if not selected:
        return doc
    symbols = [s for s in doc.get("symbols", []) if s.get("qualified_name") in selected]
    out = dict(doc)
    out["symbols"] = symbols
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a compact or detailed code IR from a Python file.")
    parser.add_argument("python_file", help="Path to a Python source file")
    parser.add_argument("--mode", choices=sorted(VALID_MODES), default=MODE_SUMMARY)
    parser.add_argument("--symbol", action="append", default=[], help="Restrict output to one or more qualified symbols")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON without indentation")
    args = parser.parse_args()

    result = extract_symbols_from_file(args.python_file, mode=args.mode)
    if args.symbol:
        result = filter_symbols(result, set(args.symbol))

    if args.compact:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
