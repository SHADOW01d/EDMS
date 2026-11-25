# Operations Manual

## Routine Commands
```sh
cd /home/dreamer/EDMS
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test
```

## Services
- Django web service: Gunicorn.
- PostgreSQL: port 5433 locally, 5432 inside Compose.
- Redis: port 6379 locally and broker port inside Compose.
- Celery worker: starts notification/report task worker; no Celery Beat is configured.

## Daily Operations
- Confirm branch reports and inventory movement totals.
- Approve daily branch reports as Manager.
- Review audit events in Django admin.
- Back up PostgreSQL.
- Review axes lockout records if accounts cannot authenticate.

## Incident Handling
- Preserve logs and database dumps.
- Disable an account via Django admin rather than deleting it.
- Do not reset migrations or restore over a live database without a verified recovery window.
- Rotate secrets after exposure.
