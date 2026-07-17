from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from pydantic import ValidationError

from agent.runtime import AgentRuntime
from agent.agent_tool_execution import validate_registered_tool_result
from config import SETTINGS, env_bool
from contracts.api import ApiErrorResponse
from tools.curl_tool import add_domain_to_whitelist
from tools.tools import TOOLS
from web.metrics_routes import register_metrics_routes


STATIC_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


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


def create_app(runtime: AgentRuntime | None = None) -> Flask:
    runtime = runtime or AgentRuntime()
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
        try:
            state = runtime.snapshot_state()
        except ValidationError:
            logger.exception("runtime state contract validation failed")
            error = ApiErrorResponse(error="Runtime state failed contract validation.")
            return jsonify(error.to_payload()), 500

        return jsonify(state.to_payload())

    @app.post("/api/messages")
    def post_message() -> Any:
        payload = request.get_json(silent=True) or {}
        content = str(payload.get("content", "")).strip()

        if not content:
            return jsonify({"ok": False, "error": "Empty message"}), 400

        started = runtime.start_generation({"role": "user", "content": content})
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
            try:
                raw_tool_result = validate_registered_tool_result(
                    str(pending.get("tool") or "curl_url"),
                    raw_tool_result,
                )
            except ValidationError:
                logger.exception("curl approval tool result contract validation failed")
                error = ApiErrorResponse(error="Curl approval result failed contract validation.")
                return jsonify(error.to_payload()), 500
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


default_runtime = AgentRuntime()
app = create_app(default_runtime)

def run() -> None:
    app.run(
        host=SETTINGS.host,
        port=SETTINGS.port,
        debug=env_bool("WALLACE_FLASK_DEBUG", False),
        threaded=True,
    )

if __name__ == "__main__":
    run()
