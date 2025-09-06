# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ЖильеGO is a Django-based Telegram bot for daily apartment rentals in Kazakhstan. The system allows users to search and book apartments, administrators to manage listings, and provides analytics. It also includes WhatsApp integration and uses Celery for background tasks.

## Common Commands

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
# Start all services (PostgreSQL, Redis, MinIO, Django, Celery)
docker-compose up -d

# View logs
docker-compose logs -f web
docker-compose logs -f celery

# Run migrations in container
docker-compose exec web python manage.py migrate

# Access Django shell
docker-compose exec web python manage.py shell
```

### Testing and Quality
```bash
# Run tests
python manage.py test

# Check Django configuration
python manage.py check
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
celery -A booking_bot worker -l info

# Start Celery beat scheduler
celery -A booking_bot beat -l info
```

## Architecture

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
- Main handlers in `telegram_bot/handlers.py` (user-facing)
- Admin handlers in `telegram_bot/admin_handlers.py`
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

### Configuration
- Environment variables loaded from `.env` file
- Multi-environment support (development/production)
- Extensive security hardening in `settings.py`
- Redis for Celery broker and result backend
- PostgreSQL as primary database

### Role-Based Access
- User roles: user, admin, super_admin
- Role-specific handlers and business logic
- Admin functionality separated in dedicated handlers

## Development Workflow

1. Use existing Django patterns and model structures
2. Follow PEP 8 coding standards with lines under 100 characters
3. State management via `profile.telegram_state` for conversation flows
4. API calls use `requests` library with JWT authentication
5. Extensive logging throughout the application
6. Security-first approach with CSRF protection and input validation