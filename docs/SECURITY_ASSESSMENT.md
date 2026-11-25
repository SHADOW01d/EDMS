# Security Assessment

## Implemented
- PostgreSQL-only database configuration.
- Django authentication, CSRF middleware, secure password hashing, password validators.
- Role checks on all operational dashboards and mutation endpoints.
- Branch object checks for transfer receipt operations.
- django-axes login failure throttling.
- Password change invalidates and logs out the current session.
- Secure password reset views.
- Immutable audit event model and read-only Django admin.
- Login success, logout, and login failure audit events.
- Sale, password, and sensitive branch activity audit hooks.
- Authenticated responses use private no-store cache headers.
- PDF and CSV values are handled through Django/ReportLab APIs.
- PostgreSQL row locks and atomic transactions on critical operations.

## Remaining
- MFA for privileged accounts is not yet implemented.
- CSP requires a template nonce strategy and external asset inventory.
- A complete account-lockout UI and reset notification should be verified with email infrastructure.
- Audit event coverage should be expanded to every procurement, production, dispatch, receipt, expense, and report approval action.
- Dependency and OWASP ZAP scans require final execution in an authorized production-like environment.
- pip-audit found no known vulnerabilities in the pinned dependency set.
- Bandit found no high-severity findings; remaining low/medium findings include test password literals and SQL-expression false positives from text/migration tooling.
