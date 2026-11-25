# Cyber Kill Chain Defense

## Reconnaissance
- Restrict admin/login technical exposure.
- Production DEBUG must remain false.
- django-axes records repeated access patterns.
- Audit authentication failures.

## Weaponization
- Review pinned dependencies with pip-audit and Bandit.
- Keep .env and private keys outside Git.
- Do not accept executable uploads.

## Delivery
- Use CSRF middleware and Django form validation.
- Use HTTPS and secure cookies.
- Limit branch and manager operations to authenticated roles.
- Apply django-axes login throttling.

## Exploitation
- Parameterized ORM queries prevent SQL injection.
- Template escaping prevents ordinary XSS.
- Server-side authorization prevents UI-only privilege bypass.
- Lock critical database rows.

## Installation
- Run the app under a non-root Docker user.
- Restrict service ports to localhost in local Compose.
- Keep database credentials in environment variables.
- Keep audit records append-oriented and admin-read-only.

## Command and Control
- Redis and PostgreSQL are not public in Compose.
- Redis uses authentication and AOF persistence.
- Restrict Celery broker access to the internal network.
- Centralized structured logging remains a residual production requirement.

## Actions on Objectives
- PostgreSQL backups and restoration scripts are provided.
- Inventory and financial operations use transactions.
- Audit events record sensitive actions.
- Role/location isolation prevents cross-branch data manipulation.
