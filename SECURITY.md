# Security

Wallace is a local-first AI agent runtime intended for defensive development
workflows and local experimentation. It is not a hardened multi-user service.

## Threat Model

Wallace assumes:

- a trusted local operator;
- a local OpenAI-compatible model server;
- local source code and runtime state controlled by the operator;
- no hostile multi-tenant users sharing the same Wallace process.

The main risks Wallace addresses are accidental unsafe tool use, prompt-driven
tool misuse, path escapes from the runtime workspace, unsafe network fetches,
and unsupported agent claims during guided workflows.

## Current Controls

- **Sandbox path boundary:** file tools resolve paths through `sandbox.py` and
  reject escapes from the configured sandbox directory.
- **Shell restrictions:** `run_shell` rejects shell control operators and only
  allows explicitly registered command shapes.
- **Tool registry:** model-visible tools are defined through explicit OpenAI
  tool schemas and a local registry.
- **Skill policy enforcement:** selected skills constrain allowed tools,
  forbidden tools, ordered tool calls, verified symbols, and OWASP final-answer
  requirements outside the model.
- **Curl approval:** external fetches require a domain whitelist and reject
  private or unsafe network targets.
- **Trace redaction:** run traces redact common sensitive key names and disable
  payload logging by default.

## Prompt Injection Boundary

Wallace does not trust prompt text as policy. Skill selection and policy checks
run outside the model, so a model instruction to skip required retrieval, write
active skill files directly, or use a blocked tool can be rejected by runtime
policy.

This is a guardrail, not a proof of safety. The local model may still produce
incorrect text, miss findings, or attempt blocked tool calls.

## Sandbox Limits

The sandbox is an application-level boundary, not an operating-system security
container. Docker Compose improves isolation for local development, but Wallace
should not be exposed as a public service without additional controls:

- authentication and authorization;
- per-user/session isolation;
- resource quotas;
- stronger process isolation;
- persistent audit logging;
- secrets management;
- network egress policy.

## Secrets

Do not commit real API keys, model server credentials, trace payloads, local
state, generated indexes, or private corpora. Use `.env.example` as the public
configuration template.

## Defensive Use Only

The OWASP security review workflow is scoped to bounded defensive static review.
It should not produce exploit payloads, offensive automation, live attack
guidance, or instructions for abusing real systems.
