# EDMS Audit Report

## Baseline
- Branch: `main`.
- Uncommitted implementation work existed before this audit.
- SQLite integrity check passed: `ok`.
- SQLite foreign-key check passed with no returned violations.
- Baseline PostgreSQL migration is isolated from unrelated local database containers.

## Critical Findings

### CRITICAL - SQLite fallback removed
- The application previously started with SQLite if `DATABASE_URL` was absent.
- Status: corrected. `DATABASE_URL` is required and the configured backend must be PostgreSQL.

### HIGH - Configuration secrets
- `.env` was absent and Compose required secrets only at runtime.
- `.env` is now ignored; `.env.example` contains placeholders only.
- Residual: production secrets and production hostnames must be supplied externally.

### HIGH - Full package sales stock decomposition
- The catalog has an ED full-package SKU plus single Effective Diet, Pressure Masala, and honey products.
- Status: branch stock cards now display the three components.
- Residual: a package sale must atomically decrement each underlying component, rather than only the bundle SKU.

### HIGH - Idempotency
- Production outputs have request keys, but purchases, dispatches, sales, and expense/call/report submissions may be vulnerable to duplicate form resubmission.
- Status: partial controls exist for some receiving operations; broader idempotency is still required.

### HIGH - Audit logging
- Django simple-history middleware is installed, but ordinary operational models do not consistently use history models.
- Status: unresolved. Structured immutable audit events are required.

### HIGH - PWA sensitive navigation caching
- The service worker currently fetches navigations and only falls back offline; it does not cache the response, but navigation behavior should explicitly avoid all authenticated page caching.
- Status: unresolved/needs verification.

### MEDIUM - Redis/Celery deployment
- Redis and Celery configuration exist, but Docker Compose does not start Django or Celery services.
- Notification/report task modules are placeholders.
- Status: unresolved operationally.

### MEDIUM - Security headers
- Production settings include HTTPS/HSTS/session secure cookies and frame denial.
- Content-Security-Policy and login throttling are not implemented.
- Status: unresolved.

### MEDIUM - Account administration
- Password changes exist, but secure reset, login throttling, account lockout, and password-change session invalidation require verification/hardening.

## Positive Findings
- Core critical operations use `transaction.atomic()` and several use `select_for_update()`.
- Purchase and transfer services block repeat receiving/deduction states.
- Role checks exist on dashboards and operational endpoints.
- Branch receiving enforces branch destination object checks.
- Django migration chain has no missing model migrations.
