# Testing Report

## Executed
- Django system checks: passed.
- Migration consistency (`makemigrations --check --dry-run`): passed.
- PostgreSQL schema migration: passed.
- SQLite-to-PostgreSQL row copy: source/target counts matched.
- Role-workspace tests: 12 passed.
- Inventory tests plus role tests: 17 passed.
- Complete Django suite: 57 passed on the PostgreSQL-backed test environment.
- Branch stock package card test: passed.
- PDF endpoint: valid `%PDF` response and 31-day range verification passed.
- PostgreSQL constraints: 0 unvalidated constraints.

## PostgreSQL Test Environment
Tests use the default `DATABASE_URL`; because PostgreSQL is the only backend, test execution is PostgreSQL-backed in configured environments.

## Remaining
- Full dashboard suite rerun after final audit changes.
- Concurrency tests for simultaneous receipt, dispatch, production, and sales.
- OWASP ZAP authorized local scan: not executed in this session.
- Bandit: no high findings; 34 low and 2 medium-confidence findings remain, including test fixture password literals and one validation-text SQL false positive.
- pip-audit: no known vulnerabilities found.
- Production deployment smoke test.
