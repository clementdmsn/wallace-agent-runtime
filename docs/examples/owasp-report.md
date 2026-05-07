# Sample OWASP Review Output

## Finding 1: Hardcoded Secret Used for Authentication

- **Severity:** High
- **File:** `app.py`
- **Evidence:** line 12 defines a static `SECRET_KEY` value used by the web app.
- **Risk:** a leaked or predictable secret can allow forged sessions or token
  abuse depending on framework usage.
- **OWASP reference:** OWASP ASVS 2.10, "Secrets Management", version 4.0.3,
  `https://owasp.org/www-project-application-security-verification-standard/`
- **Remediation:** load secrets from a protected environment or secret manager,
  rotate exposed values, and fail startup when required secrets are missing.
- **Confidence:** Medium, because this static review does not inspect deployment
  configuration.

## Review Limits

- Sample artifact for documentation; not a live scan result.
- Dependency vulnerability data was not checked.
- Runtime configuration and production secrets handling were not available.
