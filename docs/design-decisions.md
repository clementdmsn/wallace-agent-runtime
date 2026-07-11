# Design Decisions

## Local-First Runtime

Wallace is designed around a local OpenAI-compatible model server. This keeps
experimentation cheap, keeps private code local by default, and makes the
runtime easy to inspect and modify.

Tradeoff: local models vary in reliability. Wallace compensates with explicit
tool contracts, policy checks, and offline evals rather than assuming the model
will always follow instructions.

## OpenAI-Compatible Interfaces

The runtime uses OpenAI-style chat completions, streaming deltas, and function
tool schemas. This makes the core loop recognizable and portable across local
servers that expose the same API shape.

Tradeoff: provider-specific capabilities are intentionally avoided in the core
path until there is a clear need.

## Runtime Skill Routing

Skills are selected before the model call. A selected skill injects procedural
guidance and activates policy state for the current request.

This keeps workflows such as OWASP review, code explanation, and skill
authoring explicit instead of relying only on broad system-prompt text.

## External Policy Enforcement

Wallace enforces critical workflow rules outside the model:

- allowed and forbidden tools;
- ordered recommended tool calls;
- verified symbols before function explanation;
- OWASP retrieval before final security findings;
- blocked direct writes to active skill catalog files.

This design treats the model as an untrusted planner whose tool choices must be
validated by runtime code.

## Contract Validation Failure Policy

Runtime contracts are boundary checks, not best-effort hints. Validation
failures must be visible at the layer that owns the boundary:

- API and tool boundary validation failures are converted into controlled error
  responses or tool results, including `/api/state` validation failures caused
  by malformed runtime state.
- Trace validation failures are nonfatal, logged, and omitted from the trace
  stream rather than crashing the agent.
- Offline eval scenario validation failures stop execution before any scenario
  runs.
- Internal snapshot validation failures fail tests and development quality
  checks unless they are intentionally surfaced through a controlled API error
  response.
- Contract validation errors are never silently discarded.

## Deterministic Agent Evals

Offline evals exercise skill selection, execution guidance, and policy checks
without calling a model or embedding backend. They are fast enough for CI and
turn agent behavior into repeatable contracts.

Tradeoff: they do not measure model quality. They prove the runtime guards and
routing behavior around the model.

## Observability

Wallace records runtime events, tool calls, request metrics, model-call timing,
prompt-size estimates, and optional JSONL traces. The UI exposes this state so
reviewers can inspect what the agent did rather than only reading the final
answer.

## Current Limits

- one in-memory agent;
- no authentication;
- no durable multi-session backend;
- no hosted deployment target;
- no production secrets manager;
- sandboxing is application-level unless combined with Docker or stronger host
  isolation.

## Improvement Paths

- persistent sessions and trace storage;
- authenticated multi-user mode;
- stronger per-run isolation;
- richer eval dashboards;
- cost/token accounting from provider usage metadata;
- model/provider adapters beyond the current local preset.
