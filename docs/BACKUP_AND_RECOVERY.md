# Backup and Recovery

## PostgreSQL Backup
Set `DATABASE_URL`, then run:

```sh
./scripts/backup_postgres.sh
```

The script creates a timestamped custom-format dump under `backups/` and prints a SHA-256 checksum.

## PostgreSQL Restore
```sh
./scripts/restore_postgres.sh /absolute/path/edms-postgresql.dump
```

Restoration should occur on an isolated database. Verify application migration state and business totals after restore.

## SQLite Baseline Preservation
The original SQLite database and timestamped baseline backup must remain read-only historical migration sources until independent verification and a signed migration acceptance is complete.

## Restore Validation
Check:
- Migration ledger.
- User count.
- Product count.
- Inventory ledger quantity sum.
- Sales financial total.
- Purchase financial total.
- Foreign-key constraint validation.
