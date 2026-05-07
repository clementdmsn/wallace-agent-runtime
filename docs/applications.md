# Technical Applications

This document maps Wallace runtime patterns to common agent-system designs. It
is not a production deployment guide; each application would need additional
security, persistence, authentication, and operational controls.

## Defensive Security Review

**Use case:** bounded static review of application code against known security
guidance.

**Runtime pattern:** select the OWASP security review skill, discover a limited
target set, inspect code evidence, retrieve OWASP references, and block final
findings until retrieval has happened.

**Relevant components:** `skills/selection.py`, `agent/agent_skill_policy.py`,
`tools/review_target_tools.py`, `tools/owasp_reference_tools.py`,
`evals/scenarios/agent_contracts.json`.

**Limitations:** static review cannot prove exploitability, inspect deployment
secrets, or replace manual review.

## Code Understanding

**Use case:** explain a file or specific function using deterministic code
inspection before model-generated explanation.

**Runtime pattern:** route whole-file requests to `summarize_code_file`; route
function requests through `list_code_symbols` before
`explain_function_for_model`; block guessed symbols.

**Relevant components:** `tools/code_tools.py`, `skills/guidance.py`,
`agent/agent_skill_policy.py`.

**Limitations:** language support depends on the implemented parsers and the
quality of the inspected source.

## Tool-Using Developer Agent

**Use case:** local assistant that can inspect files, run bounded commands, and
surface execution state.

**Runtime pattern:** expose a small model-visible tool registry, validate tool
arguments, execute tools server-side, append hidden tool messages, and display
tool events in the UI.

**Relevant components:** `tools/schemas.py`, `tools/tools.py`,
`agent/agent_tool_execution.py`, `web/app.js`.

**Limitations:** shell access is intentionally constrained and should remain
behind stronger isolation for shared or hosted deployments.

## Retrieval-Grounded Agent Workflow

**Use case:** answer or review with local reference material instead of relying
only on model memory.

**Runtime pattern:** validate a reference corpus, build a local index, retrieve
targeted references during a selected workflow, and require returned metadata in
final claims.

**Relevant components:** `tools/owasp_reference_tools.py`,
`tools/skill_index_tools.py`, `agent/run_trace.py`.

**Limitations:** retrieved references are only as complete and current as the
local corpus.

## Agent Behavior Evaluation

**Use case:** test agent routing and policy behavior without calling a live
model.

**Runtime pattern:** replay deterministic scenario fixtures through the same
skill selection, guidance, tool-policy, and final-answer checks used at runtime.

**Relevant components:** `evals/offline_runner.py`,
`evals/scenarios/agent_contracts.json`, `tests/test_offline_evals.py`.

**Limitations:** offline evals validate runtime contracts, not model reasoning
quality.
