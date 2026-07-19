from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from pydantic import ValidationError

from agent.curl_approval import resolve_curl_approval
from agent.runtime import AgentRuntime
from config import SETTINGS, env_bool
from contracts.api import ApiErrorResponse
from web.metrics_routes import register_metrics_routes


STATIC_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


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

        response = resolve_curl_approval(runtime, approval_id, action)
        return jsonify(response.payload), response.status_code

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
