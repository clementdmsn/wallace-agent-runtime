from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from agent import Agent
from agent.agent_tool_execution import append_resolved_tool_result
from config import SETTINGS, env_bool
from tools.curl_tool import add_domain_to_whitelist
from tools.tools import TOOLS
from web.metrics_routes import register_metrics_routes


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR


class WallaceRuntime:
    def __init__(self, agent: Agent | None = None):
        self.agent = agent or Agent()
        self.worker: threading.Thread | None = None
        self.state_lock = threading.Lock()

    def start_generation(self, submitted: dict[str, Any] | None = None) -> bool:
        with self.state_lock:
            if self.agent.is_busy():
                return False
            if self.worker is not None and self.worker.is_alive():
                return False

            run_id = self.agent.reserve_generation(submitted)
            if run_id is None:
                return False

            self.worker = threading.Thread(target=self.agent.call_model, args=(run_id,), daemon=True)
            self.worker.start()
            return True

    def resume_with_resolved_tool_result(
        self,
        pending: dict[str, Any],
        tool_result: dict[str, Any],
        approval_id: str | None,
    ) -> bool:
        with self.state_lock:
            if self.agent.is_busy():
                return False
            if self.worker is not None and self.worker.is_alive():
                return False

            current_pending = self.agent.snapshot_pending_approval()
            if current_pending is None:
                return False
            if approval_id is not None and current_pending.get("approval_id") != approval_id:
                return False

            run_id = self.agent.reserve_generation()
            if run_id is None:
                return False

            cleared = self.agent.clear_pending_approval(approval_id)
            if cleared is None:
                self.agent._finish_generation(run_id)
                return False

            append_resolved_tool_result(self.agent, pending, tool_result)
            self.worker = threading.Thread(target=self.agent.call_model, args=(run_id,), daemon=True)
            self.worker.start()
            return True

# return only messages that are not system, tool or that have no context
def visible_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", "assistant"))
        if role in {"system", "tool"}:
            continue

        content = message.get("content") or ""
        if role == "assistant" and not content and message.get("tool_calls"):
            continue

        visible.append({
            "role": role,
            "content": str(content),
        })
    return visible


# return serialized list of tools events
def serialize_tool_events(tool_events: list[Any]) -> list[Any]:
    serialized: list[Any] = []
    for event in tool_events:
        if isinstance(event, (dict, list, str, int, float, bool)) or event is None:
            serialized.append(event)
        else:
            try:
                serialized.append(event.__dict__)
            except AttributeError:
                serialized.append(str(event))
    return serialized


def model_safe_curl_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and result.get("status") == "approval_required":
        return {
            "status": "error",
            "url": result.get("url"),
            "domain": result.get("domain"),
            "error": "domain is not whitelisted",
        }
    if isinstance(result, dict):
        return result
    return {"status": "error", "error": str(result)}


def create_app(
    runtime: WallaceRuntime | None = None,
    start_generation_func: Any | None = None,
) -> Flask:
    runtime = runtime or WallaceRuntime()
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
    register_metrics_routes(app, runtime)

    @app.route("/")
    def index() -> Any:
        return send_from_directory(STATIC_DIR, "index.html")

    @app.route("/styles.css")
    def styles() -> Any:
        return send_from_directory(STATIC_DIR, "styles.css")

    @app.route("/app.js")
    def app_js() -> Any:
        return send_from_directory(STATIC_DIR, "app.js")

    @app.route("/metrics.js")
    def metrics_js() -> Any:
        return send_from_directory(STATIC_DIR, "metrics.js")

    @app.get("/api/state")
    def get_state() -> Any:
        with runtime.agent.lock:
            messages = [dict(message) for message in runtime.agent.messages]
            tool_events = [dict(event) for event in runtime.agent.tool_events]
            runtime_metrics = runtime.agent.metrics.snapshot()
            last_error = runtime.agent.last_error
            is_generating = runtime.agent.is_generating
            pending_approval = dict(runtime.agent.pending_approval) if runtime.agent.pending_approval else None
            active_skill_name = runtime.agent.active_skill_name
            active_skill_policy = dict(runtime.agent.active_skill_policy or {})

        return jsonify(
            {
                "messages": visible_messages(messages),
                "tool_events": serialize_tool_events(tool_events),
                "runtime_metrics": runtime_metrics,
                "active_skill_name": active_skill_name,
                "active_skill_policy": active_skill_policy,
                "is_generating": is_generating,
                "last_error": last_error,
                "pending_approval": pending_approval,
            }
        )

    @app.post("/api/messages")
    def post_message() -> Any:
        payload = request.get_json(silent=True) or {}
        content = str(payload.get("content", "")).strip()

        if not content:
            return jsonify({"ok": False, "error": "Empty message"}), 400

        starter = start_generation_func or runtime.start_generation
        started = starter({"role": "user", "content": content})
        if not started:
            return jsonify({"ok": False, "error": "Generation already in progress"}), 409

        return jsonify({"ok": started})

    @app.post("/api/curl-approvals")
    def post_curl_approval() -> Any:
        payload = request.get_json(silent=True) or {}
        approval_id = str(payload.get("approval_id", "")).strip()
        action = str(payload.get("action", "")).strip().lower()

        if action not in {"approve", "deny"}:
            return jsonify({"ok": False, "error": "Action must be approve or deny"}), 400

        pending = runtime.agent.snapshot_pending_approval()
        if pending is not None and approval_id and pending.get("approval_id") != approval_id:
            pending = None
        if pending is None:
            return jsonify({"ok": False, "error": "No matching pending approval"}), 404

        if action == "approve":
            result = add_domain_to_whitelist(str(pending.get("domain") or ""))
            if result.get("status") != "ok":
                return jsonify({"ok": False, "error": result.get("error", "Approval failed")}), 500
            tool = TOOLS.get(str(pending.get("tool") or ""))
            if tool is None:
                return jsonify({"ok": False, "error": "Pending tool is no longer registered"}), 500
            raw_tool_result = tool.func(**dict(pending.get("args") or {}))
            if isinstance(raw_tool_result, dict) and raw_tool_result.get("status") == "approval_required":
                replaced = runtime.agent.replace_pending_approval(
                    approval_id or None,
                    str(pending.get("tool") or "curl_url"),
                    dict(pending.get("args") or {}),
                    raw_tool_result,
                    str(pending.get("call_id") or ""),
                )
                if not replaced:
                    return jsonify({"ok": False, "error": "No matching pending approval"}), 404
                return jsonify({"ok": True, "pending_approval": runtime.agent.snapshot_pending_approval()})
            tool_result = model_safe_curl_result(raw_tool_result)
        else:
            tool_result = {
                "status": "error",
                "url": pending.get("url"),
                "domain": pending.get("domain"),
                "error": "domain is not whitelisted",
                "message": "The user denied adding this domain to the curl whitelist.",
            }

        started = runtime.resume_with_resolved_tool_result(pending, tool_result, approval_id or None)
        if not started:
            return jsonify({"ok": False, "error": "Generation already in progress"}), 409

        return jsonify({"ok": True})

    @app.post("/api/reset")
    def reset_chat() -> Any:
        ok = runtime.agent.reset()
        if not ok:
            return jsonify({"ok": False, "error": "Generation in progress"}), 409
        return jsonify({"ok": True})

    @app.get("/api/reset")
    def reset_chat_get_not_allowed() -> Any:
        return jsonify({"ok": False, "error": "Use POST for reset"}), 405

    @app.get("/api/health")
    def health() -> Any:
        return jsonify({"ok": True})

    return app


default_runtime = WallaceRuntime()
agent = default_runtime.agent
worker: threading.Thread | None = None
state_lock = default_runtime.state_lock


def start_generation(submitted: dict[str, Any] | None = None) -> bool:
    global worker

    default_runtime.worker = worker
    started = default_runtime.start_generation(submitted)
    worker = default_runtime.worker
    return started


app = create_app(default_runtime, start_generation_func=lambda submitted: start_generation(submitted))

def run() -> None:
    app.run(
        host=SETTINGS.host,
        port=SETTINGS.port,
        debug=env_bool("WALLACE_FLASK_DEBUG", False),
        threaded=True,
    )

if __name__ == "__main__":
    run()
