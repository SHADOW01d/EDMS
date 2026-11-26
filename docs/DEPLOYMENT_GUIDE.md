# Deployment Guide

## Railway Deployment

### 1. Create services
Create one Railway project with:

- One PostgreSQL plugin.
- One Redis plugin.
- One web service connected to this Git repository.
- One optional worker service connected to the same repository.

Railway injects PostgreSQL variables. Map or share `DATABASE_URL` using the PostgreSQL plugin reference.

### 2. Web service settings
Use the Dockerfile builder.

Set:

```text
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=<strong random value, at least 50 characters>
ALLOWED_HOSTS=<your-railway-domain>,<optional-custom-domain>
CSRF_TRUSTED_ORIGINS=https://<your-railway-domain>,https://<optional-custom-domain>
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
DEBUG=False
```

Install Railway's PostgreSQL and Redis plugin variables before the first deployment. The web Docker command automatically runs migrations and `collectstatic`, then starts Gunicorn on Railway's `$PORT`.

Because migrations run during web startup, deploy with one web replica at a time. Before scaling to multiple web replicas, move migrations into a one-off deployment step so multiple instances do not attempt schema changes concurrently.

### 3. Worker service
Set the same Django, database, and Redis environment variables. Override the worker start command with:

```sh
celery -A config worker --loglevel=INFO
```

Do not expose the worker publicly.

### 4. Static and media files
WhiteNoise serves collected static assets. For private/uploads or persistent media, attach a Railway volume and mount it at `/app/media`.

### 5. Railway health check
Configure `/healthz/` as the web health check path. It verifies PostgreSQL connectivity.

### 6. Custom domain
Add the Railway/custom domain to both `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, using only HTTPS origins for `CSRF_TRUSTED_ORIGINS`.

### 7. Install EDMS as an app
EDMS is a Progressive Web App (PWA). Serve it over HTTPS in production; browsers only allow app installation and service workers on secure origins (localhost is allowed for development). After deployment, open the site in a supported browser and choose **Install app** when prompted, or use the browser's install option. On iPhone/iPad, open the site in Safari and choose **Share → Add to Home Screen**.

The installed app launches in a standalone window. It still needs an internet connection to sign in and use live EDMS data; offline support only provides an offline notice, not offline transactions.

### 8. Response-time guidance
- Place the web service, PostgreSQL, and Redis in the same Railway region where available. Cross-region database calls add latency to every request.
- Use Railway's service metrics and browser developer tools from the users' actual network. Compare time to first byte (server response) with total load time and the network waterfall to separate application/database delay from internet, device, and external CDN delay.
- Static assets use Django's compressed, manifest-based WhiteNoise storage. Keep collected static files on the web service and avoid placing the database or Redis on a remote network.
- Tune instance size and web worker count only after checking CPU, memory, request duration, and database connection usage under realistic concurrent use. More workers are not always faster on a memory-limited instance.
- No deployment can guarantee zero delay. User location, mobile coverage, device performance, and third-party CDN availability affect perceived speed.

---

# Local Docker Reference

## Pre-deployment
1. Copy `.env.example` to `.env` and replace every secret placeholder.
2. Set `DJANGO_SETTINGS_MODULE=config.settings.prod`.
3. Set production `ALLOWED_HOSTS` and HTTPS-aware proxy configuration.
4. Ensure `DATABASE_URL` uses PostgreSQL and no SQLite value is accepted.
5. Confirm PostgreSQL and Redis are not published externally.
6. Create a fresh PostgreSQL backup.
7. Keep database backups out of Git. The repository ignores `backups/`; store backup copies in an access-controlled location. If a backup was previously pushed to a remote repository, removing it from the current revision does not erase it from Git history.

## Build and Start
```sh
cd /home/dreamer/EDMS
docker compose build
docker compose up -d db redis
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py collectstatic --no-input
docker compose up -d web worker
```

## Verify
```sh
curl -I https://your-host/sw.js
docker compose ps
docker compose logs web worker db redis
```

## Production Stop
```sh
docker compose stop
```

Do not enable `DEBUG=True` in production.
