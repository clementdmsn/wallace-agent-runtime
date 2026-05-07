# Guided Demo: OWASP-Assisted Audit

This demo shows Wallace as a policy-governed agent runtime rather than a plain
chat wrapper. The artifacts below are representative demo artifacts backed by
offline eval contracts; they should not be read as a live scan transcript unless
explicitly regenerated from a captured run.

## Exact Prompt

```text
security audit app.py using OWASP
```

## Why This Skill Is Selected

The prompt combines a security-review action (`security audit`), a code target
(`app.py`), and an explicit OWASP domain request. Wallace parses that intent
before the model response and selects `owasp_security_review` because the skill
metadata supports defensive code review, OWASP/security tags, Python targets,
and a required `path` argument.

The selected skill injects a bounded review procedure and activates runtime
policy outside the model.

## Expected Ordered Tool Calls

For this short single-file audit, the expected tool order is:

1. `discover_review_targets` with `root: "app.py"` and `max_files: 20`.
2. `read_file_with_line_numbers` for the discovered target.
3. `search_owasp_reference` with a query based on concrete reviewed evidence.
4. Final answer with findings that cite returned OWASP reference metadata.

The compact sample trace is stored in
[`../examples/owasp-trace.json`](../examples/owasp-trace.json).

## Policy Rule

When `owasp_security_review` is active, Wallace blocks a final answer until a
successful OWASP reference lookup has been recorded:

```text
OWASP security review final answer blocked: missing search_owasp_reference call
```

The runtime message instructs the agent to call `search_owasp_reference` with
the concrete concern found in reviewed evidence, then answer using only returned
OWASP source, version, reference, title, and URL metadata for citations.

This is a runtime guarantee enforced by `agent.agent_skill_policy`, not a prompt
instruction that depends on model compliance.

## Sample Final Report

See [`../examples/owasp-report.md`](../examples/owasp-report.md).

The report is a sample documentation artifact. It is intentionally labeled with
review limits and should not be presented as a live vulnerability scan result.

## Offline Eval Scenarios

The deterministic offline suite includes scenarios for:

- OWASP review selection;
- blocked final answers before reference retrieval;
- allowed final answers after reference retrieval;
- wrong tool blocking inside the selected skill;
- sandbox/path escape protection;
- direct active skill file write protection.

Run them with:

```bash
make eval-offline
python -m evals.offline_runner --json
```

Stored eval output:

[`../examples/offline-eval-report.json`](../examples/offline-eval-report.json)
