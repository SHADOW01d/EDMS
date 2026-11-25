# Database Migration Report

## Source
- Database: SQLite `db.sqlite3`.
- Integrity: `ok`.
- Foreign-key check: no violations.
- Timestamped backup: `backups/db.sqlite3.baseline-2026-11-24.bak`.
- PostgreSQL dump: `backups/edms-postgresql-2026-11-24.dump`.

## Target
- PostgreSQL 16 on isolated local port `5433`.
- Database: `edms`.
- Docker volume: `edms_postgres_data`.

## Row Counts
- Users: 5.
- Products: 21.
- Stock locations: 3.
- Inventory ledger: 29.
- Suppliers: 3.
- Purchases: 11.
- Purchase items: 11.
- Production batches: 2.
- Production outputs: 1.
- Production consumptions: 5.
- Transfers: 3.
- Transfer items: 3.
- Sales: 6.
- Sale items: 6.
- Customers: 3.

## Totals Verified
- Inventory quantity sum: SQLite 731.000; PostgreSQL 731.000.
- Sales total: SQLite TZS 425,000.00; PostgreSQL TZS 425,000.00.
- Purchase total: SQLite TZS 602,200.00; PostgreSQL TZS 602,200.00.
- Unvalidated PostgreSQL constraints: 0.

## Migration Status
- Migration chain fully applied.
- Source/target model counts matched.
- Sequences reset for integer primary keys.
- Remaining risk: complete independent application-level workflow verification after migration.
