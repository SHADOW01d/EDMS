# EDMS Implementation Plan

## Completed
1. Repository baseline discovery.
2. SQLite integrity and row-count baseline.
3. PostgreSQL-only configuration.
4. PostgreSQL schema migration.
5. Safe SQLite-to-PostgreSQL guarded copy.
6. PostgreSQL backup and migration totals verification.
7. Branch component-stock display and package bundle display.

## Next
1. Audit and correct full-package sales to post one Effective Diet, one Pressure Masala, and one honey/can component movement.
2. Add idempotency keys for purchases, sales, dispatches, and expense/report submissions.
3. Add immutable audit event records for authentication and sensitive transactions.
4. Enforce location/object authorization for every branch mutation and export.
5. Add login throttling and session invalidation after password changes.
6. Add CSP and remove authenticated PWA navigation caching.
7. Add PostgreSQL integration tests and concurrency tests.
8. Complete Docker Compose application/worker services and health checks.
9. Add backup/restore scripts and deployment/operations documentation.

## Non-goals
- No wholesale rewrite of working dashboards.
- No deletion or reset of historical records.
- No deployment or remote push.
