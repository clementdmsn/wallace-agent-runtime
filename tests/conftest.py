from __future__ import annotations

from config import Settings
import pytest


def settings_for_sandbox(path):
    return Settings(project_dir=path, sandbox_dir=path)


@pytest.fixture(autouse=True)
def disable_agent_run_traces_for_unit_tests(monkeypatch, request):
    if request.node.path.name == 'test_run_trace.py':
        return

    import agent.agent as agent_module

    monkeypatch.setattr(agent_module.RunTrace, 'start', classmethod(lambda cls, run_id: None))
