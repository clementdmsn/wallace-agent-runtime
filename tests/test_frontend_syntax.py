from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('path', ['web/app.js', 'web/metrics.js'])
def test_browser_javascript_has_valid_syntax(path):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')

    result = subprocess.run(
        [node, '--check', path],
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr


def test_markdown_rendering_escapes_raw_html_before_inner_html():
    source = Path('web/app.js').read_text(encoding='utf-8')

    assert 'const escapedSource = escapeHtml(source);' in source
    assert 'marked.parse(escapedSource' in source
    assert 'DOMPurify.sanitize(html)' in source


def test_frontend_surfaces_api_errors_inline():
    index = Path('web/index.html').read_text(encoding='utf-8')
    app_js = Path('web/app.js').read_text(encoding='utf-8')
    metrics_js = Path('web/metrics.js').read_text(encoding='utf-8')

    assert 'id="app-error"' in index
    assert 'function showAppError(error)' in app_js
    assert 'showAppError(error);' in app_js
    assert 'showAppError(error);' in metrics_js


def test_frontend_has_chat_visible_approval_bar():
    index = Path('web/index.html').read_text(encoding='utf-8')
    app_js = Path('web/app.js').read_text(encoding='utf-8')

    assert 'id="approval-bar"' in index
    assert 'function renderApprovalBar(approval)' in app_js
    assert 'data-curl-approval-action="${action}"' in app_js
    assert 'Add domain ${escapeHtml(domain)} to the curl whitelist?' in app_js
    assert 'Requested page: ${escapeHtml(requestedUrl)}' in app_js


def test_frontend_renders_runtime_observability_overview():
    index = Path('web/index.html').read_text(encoding='utf-8')
    app_js = Path('web/app.js').read_text(encoding='utf-8')

    assert 'id="runtime-overview"' in index
    assert 'function renderRuntimeOverview(state = {})' in app_js
    assert 'state.active_skill_name || "none"' in app_js
    assert '10 offline contracts' not in app_js
    assert '<div class="overview-label">Evals</div>' not in app_js
    assert 'class="timeline-index"' in app_js
