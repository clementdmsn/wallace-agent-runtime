# OWASP Security Review

1. Treat the task as a bounded defensive static review only. Do not provide exploit payloads, offensive reproduction steps, live attack guidance, or automation for abusing a system.
2. Use the provided `path` exactly as the audit target. Call `discover_review_targets` with that path and a conservative `max_files` value, normally 20. If `discover_review_targets` fails, report the failure and stop.
3. The OWASP reference index is an admin/setup dependency. If `search_owasp_reference` reports that the index is missing or stale, report that setup/admin index rebuild is required and stop. Do not attempt to rebuild the index during a normal review.
4. Inspect only the returned target files. Prefer token-efficient context:
   - For code files, call `list_code_symbols` first when symbols are useful for orientation.
   - Call `explain_function_for_model` only for security-relevant symbols such as authentication, authorization, input handling, file/network access, serialization, cryptography, logging, or error handling.
   - Use `read_file_with_line_numbers` when findings need precise line references.
   - Use `read_file` only when line numbers are not needed. Keep evidence concise.
5. Identify candidate defensive findings only from reviewed evidence. Focus on access control, injection, input validation, authentication/session handling, cryptography, SSRF, unsafe deserialization, secrets, dependency/supply-chain indicators, logging, error handling, and insecure defaults.
6. Immediately after identifying a concrete candidate issue, call `search_owasp_reference` with a short query describing that issue, such as `hardcoded secret credential exposure` or `SQL injection from string concatenated query`. Do not cite OWASP from memory.
7. Before finalizing any finding, verify that it is supported by at least one returned OWASP reference. Every final finding must cite at least one returned OWASP reference. If no OWASP reference supports a candidate issue, either omit it or label it as a review limit rather than a finding.
8. Produce chat-only output. Do not write a report file.
9. Put findings first, ordered by severity: Critical, High, Medium, Low. For each finding include:
   - severity
   - file path
   - exact 1-based line number from `read_file_with_line_numbers`, or symbol/local evidence when line number is unavailable
   - risk
   - OWASP reference ID, title, version, source, and URL
   - remediation
   - confidence
10. If no findings are found, say so explicitly and list review limits such as file count, truncated discovery, unread files, missing runtime context, unavailable dependency vulnerability data, or missing OWASP index.
11. Mark uncertain issues as `needs manual verification`; do not overstate static-review confidence.
