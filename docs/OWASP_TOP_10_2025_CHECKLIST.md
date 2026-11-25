# OWASP Top 10:2025 Checklist

| Category | EDMS disposition |
|---|---|
| A01 Broken Access Control | Role checks and branch-location checks are present; object-level tests and audit coverage continue.
| A02 Security Misconfiguration | PostgreSQL-only settings and secure production cookie/HSTS settings exist; CSP is not yet finalized.
| A03 Software Supply Chain Failures | Dependencies are pinned to major/minor ranges and require regular `pip-audit`/version review.
| A04 Cryptographic Failures | Django password hashers and HTTPS cookie settings are used; no custom cryptography is implemented.
| A05 Injection | Django ORM and template escaping are used; raw SQL is limited to migration tooling.
| A06 Insecure Design | Critical operations use transactions and locks; idempotency is being expanded.
| A07 Authentication Failures | django-axes throttling, secure reset, password validators, and logout-after-password-change are implemented.
| A08 Software/Data Integrity Failures | Audit events, migrations, backup procedures, and request-key sales are implemented.
| A09 Security Logging/Alerting Failures | Authentication and selected operational audit events are structured; alert forwarding is a residual item.
| A10 Exceptional-Conditions | State-changing views catch domain exceptions and use redirects/messages; no stack trace is exposed in production.
