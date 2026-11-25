# EDMS System Architecture

## Runtime
- Django 5.2 application with a custom `accounts.User` model.
- PostgreSQL is the only application database. `DATABASE_URL` is required.
- Redis is configured as the Celery broker/result backend.
- Django templates render role dashboards; HTMX, Bootstrap, Alpine.js, and JavaScript provide interactions.
- PWA assets serve a manifest and service worker.

## Operational Roles
- Manager / CEO.
- Factory staff.
- Mwanza branch staff.
- Dar es Salaam branch staff.

## Apps
- `accounts`: custom user and role, login, profile, password change.
- `inventory`: products, stock locations, ledger movements, and stock balances.
- `procurement`: suppliers, purchases, purchase items, and receiving.
- `production`: recipes, batch approvals, outputs, and raw-material consumption.
- `distribution`: branch dispatches and receiving.
- `sales`: sales and sale items.
- `customers`: customers, calls, branch expenses, and daily reports.
- `dashboard`: role dashboards and operational transaction endpoints.
- `reports`: PDF/CSV exports and report tasks.
- `notifications`: notification models and task placeholders.

## Critical Data Flow
Purchase -> receive into factory -> active/approved production batch -> material consumption -> production output -> factory transfer -> branch receipt -> branch sale -> daily report.

## Inventory Model
Every stock change is represented by `InventoryLedger` and should have a traceable movement, quantity, location, reference, and optional production batch.

## Database
- PostgreSQL port 5433 is the isolated local EDMS database.
- SQLite is retained only as the migration source backup and must not be an application fallback.
- The baseline SQLite backup is stored under `backups/`.

## Deployment Topology
- Django currently runs through `manage.py runserver` locally.
- PostgreSQL and Redis run as Docker Compose services.
- The Compose file has not yet been extended with Django and Celery application services.
