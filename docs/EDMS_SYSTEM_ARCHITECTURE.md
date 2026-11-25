# EDMS System Architecture

## Runtime
- Django 5.2 application with a custom `accounts.User` model.
- PostgreSQL is the only application database. `DATABASE_URL` is required.
- Redis is used by Celery for background jobs.
- Django templates render role dashboards; HTMX, Bootstrap, Alpine.js, and JavaScript provide interactions.
- PWA assets serve a manifest and service worker.

## System Structure
- `config/`: URL routing, settings, WSGI/ASGI entry points, and Celery configuration.
- `templates/`, `static/`: server-rendered UI, styles, JavaScript, and PWA assets.
- `media/`: user-uploaded files; use persistent storage in deployed environments.
- `Dockerfile`, `docker-compose.yml`, `railway.toml`: container build, local services, and Railway deployment configuration.
- `docs/`: architecture and deployment guidance.

## Operational Roles
- Manager / CEO.
- Factory manager/staff.
- Branch managers and staff (including Mwanza and Dar es Salaam).

## Apps
- `accounts`: custom user and role, login, profile, and password change.
- `core`: shared application functionality.
- `inventory`: products, stock locations, ledger movements, and stock balances.
- `procurement`: suppliers, purchases, purchase items, and receiving.
- `production`: recipes, batch approvals, outputs, and raw-material consumption.
- `distribution`: branch dispatches and receiving.
- `sales`: sales and sale items.
- `customers`: customers, calls, branch expenses, and customer activity.
- `dashboard`: role dashboards and operational transaction endpoints.
- `reports`: report views and PDF/CSV generation.
- `notifications`: notification models and related functionality.

## Critical Data Flow
Purchase -> receive into factory -> active/approved production batch -> material consumption -> production output -> factory transfer -> branch receipt -> branch sale -> daily report and management reporting.

## Inventory Model
Every stock change is represented by `InventoryLedger` and should have a traceable movement, quantity, location, reference, and optional production batch.

## Database
- PostgreSQL is the only application database. The local Compose configuration maps it to `127.0.0.1:5433`.
- SQLite is not an application fallback.
- Database backups are operational data, not source code. Keep them out of Git and store them in an access-controlled backup location. The `backups/` directory is Git-ignored; ignoring files does not remove copies already present in Git history.

## Deployment Topology
- Local Docker Compose runs PostgreSQL, Redis, the Django/Gunicorn web service, and a Celery worker. Persistent volumes are configured for database data, Redis data, and media.
- Railway deployment uses the Dockerfile for the web service and can run a separate Celery worker with managed PostgreSQL and Redis.
- Production settings disable debug mode, require a strong secret key and allowed hosts, and enable HTTPS-related security settings.
- Dashboard stock, sales, and production summaries use grouped database aggregates rather than per-product query loops to keep dashboard query counts stable as the catalog grows.
- The container startup command runs migrations and collects static files before starting Gunicorn. Keep deployments to a single web replica during startup migrations; multi-replica deployments should run migrations once as a separate deployment step.
- Deployment configuration is not the same as a live deployment. Configure production secrets, persistent media storage, domains, and backups in the target environment.
