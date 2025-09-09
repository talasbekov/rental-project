# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ЖильеGO is a Django-based Telegram bot for daily apartment rentals in Kazakhstan. The system allows users to search and book apartments, administrators to manage listings, and provides analytics. It also includes WhatsApp integration and uses Celery for background tasks.

## Quick Start

### Onboarding (for Claude Code)

1. **Python 3.12.x** - Create `.env` from `.env.example` and fill in secrets (see "Environment")
2. **Install dependencies:**
   - Locally: `pip install -r requirements.txt -r requirements-dev.txt`
   - Or via Docker: `docker-compose up -d --build`
3. **Run migrations:** `python manage.py migrate`
4. **(Optional) Create superuser:** `python manage.py createsuperuser`
5. **Run services:**
   - API/Admin: `python manage.py runserver 0.0.0.0:8000`
   - Bot (polling): `python booking_bot/telegram_bot/main.py` 
   - Celery worker: `celery -A booking_bot worker -l info -Q default,notifications,payments`
   - Celery beat: `celery -A booking_bot beat -l info`
6. **Tests and linters:**
   - `pytest -q`
   - `ruff check . && ruff format --check .`
   - Alternative: `black . && isort . && flake8 .`

### Key Dependencies
- Django 5.x
- Django REST Framework
- Celery
- Redis
- psycopg2-binary
- python-telegram-bot
- boto3 (S3/MinIO)

## Environment Configuration

```dotenv
# Core / Django
DJANGO_SETTINGS_MODULE=booking_bot.settings
DJANGO_DEBUG=1
SECRET_KEY=<django_secret_key>
ALLOWED_HOSTS=127.0.0.1,localhost
TIME_ZONE=Asia/Almaty

# Database
POSTGRES_DB=<db_name>
POSTGRES_USER=<db_user>
POSTGRES_PASSWORD=<db_password>
POSTGRES_HOST=<db_host>
POSTGRES_PORT=5432

# Redis / Celery
REDIS_URL=redis://<redis_host>:6379/0
CELERY_BROKER_URL=${REDIS_URL}
CELERY_RESULT_BACKEND=${REDIS_URL}
CELERY_TIMEZONE=Asia/Almaty
CELERY_QUEUES=default,notifications,payments

# S3/MinIO
S3_ENDPOINT_URL=http://localhost:9000
S3_BUCKET=photos
S3_ACCESS_KEY=minio_access_key
S3_SECRET_KEY=minio_secret_key
S3_REGION=us-east-1
S3_USE_SSL=0

# Telegram Bot
TELEGRAM_BOT_TOKEN=<telegram_token>
TELEGRAM_USE_WEBHOOK=0
TELEGRAM_WEBHOOK_URL=<public_https_url>/telegram/webhook

# API Base
API_BASE=http://127.0.0.1:8000/api/v1
JWT_ACCESS_TTL_MIN=30
JWT_REFRESH_TTL_DAYS=7

# Payments
KASPI_API_BASE=<kaspi_base>
KASPI_API_KEY=<kaspi_key>
KASPI_MERCHANT_ID=<merchant_id>
KASPI_SANDBOX=1

# Photo limits
PHOTO_MAX_SIZE=5242880
```

## Architecture Deep Dive

### Core Structure
- **booking_bot/**: Main Django project
  - **users/**: User management and authentication (UserProfile with telegram_state)
  - **listings/**: Property/apartment listings, cities, districts
  - **bookings/**: Booking management and business logic
  - **payments/**: Kaspi payment gateway integration
  - **telegram_bot/**: Telegram bot handlers and utilities
  - **whatsapp_bot/**: WhatsApp Business API integration
  - **notifications/**: Centralized notification system
  - **core/**: Shared utilities, security, storage

### Key Components

**Telegram Bot Architecture:**
- Main handlers in `telegram_bot/handlers.py` (139KB, user-facing)
- Admin handlers in `telegram_bot/admin_handlers.py`  
- Edit handlers in `telegram_bot/edit_handlers.py`
- User review handlers in `telegram_bot/user_review_handlers.py`
- Bot entry point in `telegram_bot/main.py`
- Centralized callback query handling in `callback_query_handler`
- User state management via `UserProfile.telegram_state` JSON field
- JWT authentication with token refresh in `_get_profile` function

**API Communication:**
- Bot communicates with Django backend via REST API
- Base URL configured in `settings.API_BASE`
- Authentication via JWT tokens stored in user state

**Background Tasks:**
- Extensive Celery beat schedule for automated tasks:
  - Daily review requests and booking status updates
  - Check-in/check-out reminders
  - Occupancy monitoring and KO-factor analysis
  - Calendar management and cleanup

**Storage:**
- S3/MinIO integration for photo storage
- Custom storage backend at `booking_bot.core.storage.S3PhotoStorage`
- Photo optimization with max size limits and thumbnails

### Database Models
- **UserProfile**: Extended user model with Telegram integration and role management
- **Property**: Rental properties with calendar availability
- **Booking**: Booking lifecycle management with status tracking
- **Payment**: Kaspi gateway integration for transactions

### FSM Flow
```
Start (/start)
  -> City selection
    -> District selection
      -> Listings page (pagination)
        -> Select listing
          -> Choose dates
            -> Confirm booking
              -> Payment
                -> Done + Notifications
```

### FSM Rules
- callback_data must map 1:1 with handler
- FSM state stored in profile.telegram_state
- Transitions must be logged

### Role-Based Access
- User roles: user, admin, super_admin
- Role-specific handlers and business logic
- Admin functionality separated in dedicated handlers

## Development Commands

### Development Setup
```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

### Docker Development
```bash
# Quick start
cp .env.example .env && docker-compose up -d --build

# Start all services (PostgreSQL, Redis, MinIO, Django, Celery)
docker-compose up -d

# View logs
docker-compose logs -f web
docker-compose logs -f celery
docker-compose logs -f celery-beat

# Run migrations in container
docker-compose exec web python manage.py migrate

# Access Django shell
docker-compose exec web python manage.py shell
```

### Testing and Quality
```bash
# Run tests
pytest -q
python manage.py test

# Check Django configuration
python manage.py check

# Linting and formatting (Ruff - preferred)
ruff check .
ruff format --check .

# Alternative linting (Black + isort + flake8)
black . --check
isort . --check-only
flake8 .
```

### Custom Management Commands
```bash
# Setup Telegram bot menu
python manage.py setup_bot_menu

# Generate audit report
python manage.py audit_report

# Fix user profiles (custom command)
python manage.py fix_user_profile
```

### Celery Tasks
```bash
# Start Celery worker
celery -A booking_bot worker -l info -Q default,notifications,payments

# Start Celery beat scheduler
celery -A booking_bot beat -l info
```

#### Celery Queues
- **default** — general tasks
- **notifications** — messaging/notifications
- **payments** — payment-related tasks

#### Celery Beat Examples
- review-request: daily 12:00
- process-notifications: every minute
- check-expired-bookings: every 5 minutes
- monthly-report: 1st of month 09:00

## Development Workflow

### Core Principles
1. Use existing Django patterns and model structures
2. Follow PEP 8 coding standards with lines under 100 characters (configured in pyproject.toml)
3. State management via `profile.telegram_state` for conversation flows
4. API calls use `requests` library with JWT authentication
5. Extensive logging throughout the application
6. Security-first approach with CSRF protection and input validation
7. Use Ruff for linting/formatting (primary), Black+isort+flake8 available as alternative

### Storage Rules
- All photos → S3/MinIO
- Must upload successfully before saving DB record
- Public access only via presigned URLs
- Enforce PHOTO_MAX_SIZE, thumbnails

### API Documentation
- Swagger/OpenAPI: http://127.0.0.1:8000/api/docs/
- Admin Panel: http://127.0.0.1:8000/admin/

### Sample Data
```bash
python manage.py createsuperuser
```

## Git / PR Workflow
- Branches: main, develop, feat/*, fix/*
- Conventional Commits
- PR checklist:
  - [ ] Tests & linters pass
  - [ ] Migrations ok
  - [ ] Fixtures updated
  - [ ] Tests added for business logic
  - [ ] Docs updated

## Claude Code Recipes

### Adding New Telegram Handler
1. Add handler function in `telegram_bot/handlers.py` or create new handler file
2. Register handler in `telegram_bot/main.py`
3. Update keyboards and FSM states
4. Add corresponding test

### Working with User State
```python
# Get user profile with state
profile = _get_profile(user_id)
state = profile.telegram_state

# Update state
state['current_step'] = 'selecting_dates'
profile.save()
```

### API Communication Pattern
```python
headers = {'Authorization': f'Bearer {profile.access_token}'}
response = requests.get(f"{settings.API_BASE}/endpoint/", headers=headers)
```

## Troubleshooting

### Common Issues
- **Buttons not working**: check callback_data and state mapping
- **Photo upload fails**: verify S3_* environment variables
- **Celery stuck**: verify Redis connection and queue configuration
- **JWT expired**: check token refresh logic in `_get_profile`
- **FSM broken**: verify state transitions and logging

### Debugging Tools
- Django logs: logs/django.log
- Celery monitoring: `flower --broker=redis://localhost:6379/0 --port=5555`
- Web UI: http://localhost:5555
- Django shell: `python manage.py shell`
- Check bot main.py directly for debugging

## Security

- Never commit .env files
- Use environment-specific settings
- Rotate API keys regularly
- Validate all user inputs
- Use HTTPS in production
- Implement rate limiting

## Monitoring

- Django logs: logs/django.log
- Celery monitoring: flower dashboard
- Database performance monitoring
- API response time tracking
- Bot conversation flow analytics

## Makefile (optional)
```makefile
.PHONY: up down logs web celery beat test lint fmt

up:        ; docker-compose up -d --build
down:      ; docker-compose down
logs:      ; docker-compose logs -f --tail=200 web
web:       ; docker-compose exec web bash
celery:    ; docker-compose logs -f celery
beat:      ; docker-compose logs -f celery-beat
test:      ; pytest -q
lint:      ; ruff check .
fmt:       ; ruff format .
```

## 🔒 Code Quality Guardrails for Claude Code

### General Rules
- ❌ **No hallucinations**: если данных нет — прямо ответь "недостаточно информации".  
- ✅ **Рабочий код only**: только корректные, запускаемые примеры без псевдокода.  
- ✅ **Минимум абстракций**: используй самые простые и проверяемые решения.  
- ✅ **Безопасность**: не логируй секреты, используй `ENV` переменные.  
- ✅ **Оптимальность**: избегай N+1, ненужных циклов, неоптимичных запросов.  
- ✅ **Портируемость**: код должен запускаться локально без сторонних сервисов (если нужны — укажи моки).

### Output Format
1. **Context** — кратко, что делаем (2–5 строк).  
2. **Dependencies** — список библиотек + команды установки.  
3. **Code** — цельный блок, готовый к запуску.  
4. **Tests/Checks** — команда для проверки или минимальные автотесты.  
5. **Limits** — явные упрощения/ограничения.  

### Checklist Before Answer
- [ ] Нет выдуманных API/функций.  
- [ ] Код проходит линтер и запускается.  
- [ ] Есть валидация и обработка ошибок.  
- [ ] Секреты вынесены в ENV.  
- [ ] Есть инструкция запуска/проверки.  

💡 Если информации недостаточно для корректной реализации — Клауд обязан вежливо отказаться и запросить недостающие вводные.

