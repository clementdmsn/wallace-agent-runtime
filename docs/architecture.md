# Wallace Architecture

This document describes the active application code in this repository.

`sandbox/` is runtime-owned state and is excluded from source architecture. Canonical active skill definitions live under `skill_catalog/`; generated drafts, indexes, logs, and working files remain ignored in `sandbox/`.

## Runtime Spine

```text
Browser
  -> web/web_app.py
    -> agent/agent.py
      -> skills/skills.py runtime skill selection
      -> OpenAI-compatible chat API
      -> agent/agent_tool_execution.py
        -> tools/tools.py registry
          -> tools/basic_tools.py
          -> tools/code_tools.py
          -> tools/skill_index_tools.py
          -> tools/skill_authoring_tools.py
          -> tools/schemas.py
      -> agent/agent_skill_policy.py
        -> skills/ guidance and policy state
```

## Entry Points

- `main.py`: canonical local entry point.
- `web/web_app.py`: Flask app, routes, static file serving, and one global `Agent`.
- `make run`: preferred local run command.

The app currently uses one in-memory `Agent`. Restarting `python main.py` or `make run` creates a fresh conversation state.

## Web Layer

Files:

- `web/web_app.py`
- `web/index.html`
- `web/app.js`
- `web/styles.css`

Responsibilities:

- serve the browser UI
- expose `/api/state`, `/api/messages`, `/api/reset`, and `/api/health`
- start the model loop in a worker thread
- render chat messages and compact runtime/tool events

There is no persistent multi-session backend yet. The sidebar represents the current in-memory conversation.

## Agent Layer

Files:

- `agent/agent.py`
- `agent/agent_tool_execution.py`
- `agent/agent_skill_policy.py`
- `agent/model_streaming.py`
- `agent/run_trace.py`

Responsibilities:

- `agent.py`: conversation state, runtime skill selection, per-request system prompt assembly, and run lifecycle
- `agent_tool_execution.py`: decode model tool calls, execute registered tools, append hidden tool messages, emit UI events
- `agent_skill_policy.py`: active skill state, policy validation, verified symbol tracking
- `model_streaming.py`: streamed content and tool-call reconstruction
- `run_trace.py`: optional JSONL request tracing

Important runtime state:

- `messages`
- `tool_events`
- `is_generating`
- `run_id`
- `last_error`
- active skill policy fields
- active skill selection and temporary request system prompt

`run_id` is used to ignore stale work after resets or overlapping generation attempts.

## Tool Layer

Files:

- `tools/tools.py`
- `tools/basic_tools.py`
- `tools/code_tools.py`
- `tools/embedding.py`
- `tools/owasp_reference_tools.py`
- `tools/review_target_tools.py`
- `tools/schemas.py`
- `tools/skill_authoring_tools.py`
- `tools/skill_index_tools.py`
- `tools/tool_registry.py`

Responsibilities:

- `tools/tools.py`: public registry/facade consumed by the agent
- `tools/basic_tools.py`: sandboxed shell/file operations
- `tools/code_tools.py`: deterministic code inspection tools
- `tools/embedding.py`: OpenAI-compatible embedding calls
- `tools/owasp_reference_tools.py`: sandbox OWASP corpus validation, FAISS index rebuild, and reference search
- `tools/review_target_tools.py`: bounded security-review target discovery
- `tools/schemas.py`: OpenAI tool-call schemas
- `tools/skill_authoring_tools.py`: create skill metadata/procedure files and refresh indexes
- `tools/skill_index_tools.py`: FAISS skill index creation, rebuild, and search
- `tools/tool_registry.py`: `Tool` wrapper

Current exposed tool groups:

- shell/file: `run_shell`, `find_file`, `read_file`, `write_file`, `append_to_file`, `replace_in_file`, `remove_file`
- code inspection: `summarize_code_file`, `list_code_symbols`, `explain_function_for_model`
- external reference fetching: `curl_url`
- security review support: `discover_review_targets`, `search_owasp_reference`
- skill authoring: `create_skill`, `repair_skill_draft`, `finalize_skill_draft`

Runtime/internal registered tools that are not model-exposed OpenAI tools:

- skill indexing: `create_skill_faiss_index`, `search_skill_faiss_index`, `rebuild_skill_faiss_index`
- OWASP index administration: `validate_owasp_corpus`, `rebuild_owasp_reference_index`

Skill routing is no longer a model-visible tool. The runtime selects skills before the model call, injects the selected procedure into a temporary request system prompt, and sets active skill policy state for tool validation. If no skill passes routing, the model receives only the base system prompt.

`rm` is intentionally not exposed through `run_shell`; deletion goes through `remove_file`.

## Skill System

Files:

- `skills/skills.py`
- `skills/intent.py`
- `skills/loader.py`
- `skills/selection.py`
- `skills/guidance.py`
- `skills/stats.py`
- `skills/skills_registry.py`

Responsibilities:

- `skills.py`: compatibility facade and in-memory registry
- `intent.py`: conservative intent, path, action, speech-act, and symbol extraction
- `loader.py`: load versioned active skill metadata/procedure files from the skill catalog into `Skill` objects
- `selection.py`: cheap lexical pre-gate, FAISS retrieval, hard syntax validation, scoring, and ranked choice
- `guidance.py`: convert selected skills into allowed tools, forbidden tools, and recommended tool order
- `stats.py`: runtime feedback counters and selection bonus
- `skills_registry.py`: `Skill` dataclass

Skills are core functionality. They constrain and guide the local model so common tasks follow known workflows instead of relying only on prompt text.

Selection policy:

- Questions receive a strong penalty; skills are primarily for instruction-style requests.
- A cheap lexical gate skips embedding/FAISS search when no loaded skill could plausibly match the current user message.
- Candidates with missing required inputs are rejected instead of merely down-ranked.
- Skills with declared supported actions are penalized when the user request has a different known action.

Canonical active skill sources live in the project-owned catalog and are versioned:

- `skill_catalog/metadatas/*.json`
- `skill_catalog/procedures/*.md`

Wallace reads and writes the catalog through the skill-authoring tools. Generated skill state lives under the runtime sandbox and is ignored:

- `sandbox/skills/drafts/`
- `sandbox/skills/indexes/skills.faiss`
- `sandbox/skills/indexes/skills.map.json`

OWASP-backed review knowledge also lives under the runtime sandbox:

- `knowledge_base/owasp/corpus.jsonl`
- `knowledge_base/owasp/indexes/owasp.faiss`
- `knowledge_base/owasp/indexes/owasp.map.json`

`create_skill` validates metadata and procedure quality before writing files. It rejects question-shaped routing text, unknown input names, unknown required tools, missing examples, empty `when_not_to_use`, high broad `default_score` values, required tools missing from the procedure, and code skills that do not exclude nearby task types they do not handle.

## Sandbox Boundary

Files:

- `sandbox.py`
- runtime directory from `WALLACE_SANDBOX_DIR`

Responsibilities:

- validate relative sandbox paths
- block path escapes
- validate allowed shell commands
- ensure the sandbox directory exists

The sandbox directory is runtime state. Do not delete it blindly because it may contain generated indexes, logs, drafts, and local working files needed by a running Wallace instance.

## System Prompt

Files:

- `system_prompt/system_prompt.py`
- `system_prompt/system_prompt.md`

`system_prompt/system_prompt.py` builds the base system prompt from the active constitution files. It also builds temporary per-request system prompts when a skill is selected. Archived prompt fragments are historical and not active unless explicitly wired back in.

## Configuration

File:

- `config.py`

Responsibilities:

- model name
- OpenAI-compatible base URL and API key
- sandbox path
- tool timeout and output limits
- project-owned skill metadata/procedure paths
- sandbox-owned skill index paths

## Tests

Project commands:

- `make check`: compile/import sanity check for active Python modules
- `make test`: run pytest
- `make quality`: compile checks, browser JavaScript syntax checks, Ruff,
  coverage gate, and offline evals

Current tests cover:

- `sandbox.safe_path`
- `sandbox.validate_command`
- `tools.basic_tools.remove_file`
- `skills.intent.extract_intent`
- `skills.guidance.build_execution_guidance`
- runtime skill selection and prompt injection
- skill authoring validation
- tool execution and metrics
- run trace writing and summarization
- web app routes and frontend syntax

## Current Boundary Summary

- The runtime uses one in-memory agent and has no durable session backend.
- The sandbox is an application-level boundary unless Docker or stronger host
  isolation is added.
- Skill selection is a runtime pre-model step, not a model-called tool.
