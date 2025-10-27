# ЖильеGO Backend Skeleton

Django 5 project skeleton with domain apps prepared for the ЖильеGO rental platform. This repository currently contains structure and configuration only (no models yet).

## Structure

```
rental-project/
├── config/               # Django project configuration (settings, URLs, Celery)
│   ├── celery.py
│   ├── __init__.py
│   ├── asgi.py
│   ├── urls.py
│   ├── wsgi.py
│   └── settings/
│       ├── base.py
│       ├── dev.py
│       └── prod.py
├── apps/
│   ├── analytics/
│   ├── bookings/
│   ├── finances/
│   ├── notifications/
│   ├── properties/
│   └── users/
├── manage.py
├── requirements.txt
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

## Getting started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DJANGO_SETTINGS_MODULE=config.settings.dev
python manage.py migrate
python manage.py runserver
```

Docker-based startup:

```bash
cp .env.example .env
docker compose up --build
```

## Services

- PostgreSQL (db)
- Redis (redis)
- Django app (web)
- Celery worker (celery)

JWT authentication is configured via `djangorestframework-simplejwt`. Celery uses Redis broker/result backend. Environment-specific settings live under `config/settings/`.
