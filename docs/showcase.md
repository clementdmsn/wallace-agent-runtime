# Wallace Technical Showcase

Wallace is a local OpenAI-compatible agent runtime with streamed tool calls, sandboxed execution, runtime skill routing, policy enforcement, observability, and deterministic offline agent evals.

## What It Demonstrates

| Capability | Where to look | Why it matters |
|---|---|---|
| Agent run loop | `agent/agent.py` | Multi-turn agent orchestration with streamed model calls and tool execution. |
| Tool calling | `agent/agent_tool_execution.py`, `tools/schemas.py` | OpenAI function-call schemas, hidden tool messages, runtime events, and error handling. |
| Sandboxed execution | `sandbox.py`, `tools/basic_tools.py` | Path validation, shell command allowlisting, and explicit file mutation tools. |
| Skill routing | `skills/selection.py`, `skills/guidance.py` | Runtime-selected procedures with scoring, syntax validation, and task-specific guidance. |
| Policy enforcement | `agent/agent_skill_policy.py` | Allowed tools, forbidden tools, ordered tool calls, verified symbols, and final-answer guards. |
| Retrieval/indexing | `tools/skill_index_tools.py`, `tools/owasp_reference_tools.py` | FAISS-backed retrieval for skills and local security references. |
| Human approval | `tools/curl_tool.py`, `web/web_app.py` | Whitelisted URL fetching with approval flow and private-address protection. |
| Observability | `agent/agent_metrics.py`, `agent/run_trace.py`, `web/metrics_routes.py` | Timing, prompt-size estimates, tool-call metrics, and JSONL traces. |
| Agent evals | `evals/offline_runner.py`, `evals/scenarios/agent_contracts.json` | Deterministic behavior contracts for selection, guidance, and policy. |
| Quality gate | `Makefile`, `.github/workflows/quality.yml` | Compile checks, frontend syntax checks, Ruff, coverage, offline evals, and CI. |

## Run It

Start the local app with Docker Compose:

```bash
docker compose up --build
```

The UI listens on:

```bash
http://127.0.0.1:8000
```

Run the full local quality gate:

```bash
make quality
```

Run only the deterministic offline agent evals:

```bash
make eval-offline
```

Emit eval results as JSON for CI or reporting:

```bash
python -m evals.offline_runner --json
```

## Demo Scenarios

For the strongest guided demo, use the OWASP audit walkthrough in
[`docs/demo/owasp-audit.md`](docs/demo/owasp-audit.md). It includes the prompt,
expected skill selection, policy enforcement points, a sample trace, and a
sample final report.

### 1. Whole-File Code Explanation

Prompt:

```text
Explain auth.py
```

Expected runtime behavior:

- selects a code explanation skill when available
- treats the task as `whole_file_code_overview`
- recommends `summarize_code_file`
- blocks raw `read_file` in that skill context

Offline eval:

```text
whole_file_code_overview_uses_summary_tool
```

### 2. Function Explanation With Symbol Verification

Prompt:

```text
Explain function login in auth.py
```

Expected runtime behavior:

- extracts the explicit user-requested symbol
- recommends `list_code_symbols` before `explain_function_for_model`
- blocks direct function explanation until the symbol is discovered
- prevents the model from substituting a guessed symbol

Offline eval:

```text
function_explanation_requires_symbol_discovery
function_explanation_blocks_unrequested_symbol
```

### 3. OWASP Security Review

Prompt:

```text
security audit app.py using OWASP
```

Expected runtime behavior:

- forces `owasp_security_review` for explicit security-audit intent
- recommends `discover_review_targets`
- requires `search_owasp_reference` before final audit answers
- blocks OWASP citations from memory

Offline eval:

```text
owasp_review_requires_reference_search_before_final
owasp_review_allows_final_after_reference_search
owasp_review_blocks_wrong_tool_before_discovery
owasp_review_blocks_path_escape_target
owasp_review_blocks_hallucinated_reference_answer
```

### 4. Skill Authoring

Prompt:

```text
create a reusable skill for debugging functions
```

Expected runtime behavior:

- selects the skill-authoring workflow only for explicit skill-authoring requests
- routes creation through `create_skill`, `repair_skill_draft`, and `finalize_skill_draft`
- blocks direct writes to active `skill_catalog/metadatas` and `skill_catalog/procedures` paths

Offline eval:

```text
skill_authoring_blocks_direct_active_skill_writes
```

### 5. General Question Without Skill Policy

Prompt:

```text
what is your favorite debugging approach?
```

Expected runtime behavior:

- does not select a task-specific skill
- does not activate skill policy
- leaves normal tool discipline available

Offline eval:

```text
general_question_does_not_activate_skill_policy
```

### 6. Curl Approval Flow

Prompt:

```text
Fetch https://docs.python.org/3/ as reference material.
```

Expected runtime behavior:

- requires the domain to be whitelisted before fetching
- asks for user approval for new domains
- stores the whitelist outside the sandbox
- rejects private or unsafe network targets

Relevant files:

- `tools/curl_tool.py`
- `web/web_app.py`
- `tests/test_curl_tool.py`

## Agent Engineering Signals

This project is meant to show production-oriented agent engineering rather than a thin chat wrapper:

- runtime tool contracts are explicit and tested
- agent workflows are selected before the model call
- policy is enforced outside the model
- retrieval-backed workflows avoid citation-by-memory
- sandbox boundaries reduce local execution risk
- metrics and traces make agent behavior inspectable
- offline evals turn agent behavior into repeatable contracts

## Verification Snapshot

The local quality gate is:

```text
make quality
coverage gate: 82%
Offline Agent Eval Report: pass, 10/10
```
