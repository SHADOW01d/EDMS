# PostgreSQL Setup

## Requirements
- PostgreSQL 16.
- `DATABASE_URL` using `postgresql://` or `postgres://`.
- The application will fail if `DATABASE_URL` is missing or is not PostgreSQL.

## Local Docker Setup
1. Copy `.env.example` to `.env`.
2. Set strong `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, and `SECRET_KEY` values.
3. Run `docker compose up -d db redis web worker`.
4. Run `docker compose exec web python manage.py migrate`.
5. Run `docker compose exec web python manage.py collectstatic --no-input`.

The isolated local EDMS database uses host port `5433`; PostgreSQL inside Compose listens on `5432`.

## Application Database Role
Use the dedicated `edms` role. Never use the PostgreSQL superuser for application connections.

## Connection Settings
- `DB_CONN_MAX_AGE=60`
- `DB_CONNECT_TIMEOUT=10`
- Django uses a 30-second statement timeout.
