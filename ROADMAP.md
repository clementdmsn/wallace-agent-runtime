# Roadmap

Wallace is currently a local-first agent runtime. The next milestones turn it
into a more complete operational system.

## Near Term

- Improve the observability sidebar with clearer timelines, selected skill
  state, policy status, tool latency, and eval status.
- Add more deterministic offline eval scenarios for blocked tools, premature
  answers, hallucination guards, sandbox escapes, and skill-catalog write
  protection.
- Expand the guided OWASP security review demo with additional captured runtime
  traces where they add evidence beyond the existing sample trace and evals.
- Keep README, showcase, security notes, and architecture notes aligned with
  actual runtime behavior.

## Product Hardening

- Add persistent sessions and conversation history.
- Store traces in an inspectable backend instead of local JSONL files only.
- Add authentication and authorization for any non-local deployment.
- Add per-user or per-session sandbox isolation.
- Add explicit resource limits for long-running tools.

## Agent Quality

- Add richer eval metrics and scenario categories.
- Track eval history in CI artifacts.
- Add model-quality evals separate from deterministic runtime contract evals.
- Add cost/token accounting from provider usage metadata when available.

## Deployment

- Keep Docker Compose as the supported local workflow.
- Define a hardened deployment profile only after authentication, session
  isolation, trace storage, and network egress policy exist.

## Non-Goals for the Current Version

- Public hosted SaaS deployment.
- Multi-tenant security guarantees.
- Offensive security automation.
- Replacing human security review or code review.
