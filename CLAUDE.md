# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ЖильеGO** is a Django 5-based rental property platform (like Airbnb) for Kazakhstan, starting with Astana. The platform handles property listings, bookings with payment processing (Kaspi Pay), user management with roles, and background tasks via Celery.

## Essential Commands

### Development Setup

```bash
# Initial setup (local)
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DJANGO_SETTINGS_MODULE=config.settings.dev
python manage.py migrate
python manage.py runserver

# Docker setup
cp .env.example .env
docker compose up --build
```

### Testing

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test apps.users
python manage.py test apps.properties
python manage.py test apps.bookings

# Run single test
python manage.py test apps.users.tests.test_auth_api.AuthAPITests.test_register_returns_tokens
```

### Database

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### Celery

```bash
# Start Celery worker (dev)
celery -A config.celery worker --loglevel=info

# Celery beat (scheduled tasks)
celery -A config.celery beat --loglevel=info
```

## Architecture

### Project Structure

```
rental-project/
├── config/               # Django project root
│   ├── settings/         # Split settings (base, dev, prod)
│   ├── celery.py         # Celery app configuration
│   ├── urls.py           # Root URL configuration
│   ├── wsgi.py / asgi.py # WSGI/ASGI entry points
├── apps/                 # Domain-driven app structure
│   ├── users/            # Authentication, User model with roles
│   ├── properties/       # Property listings, photos, amenities
│   ├── bookings/         # Bookings, reviews, overlap prevention
│   ├── analytics/        # Analytics and reporting (future)
│   ├── notifications/    # Email/Telegram notifications (future)
│   └── finances/         # Payment processing, payouts (future)
└── manage.py
```

### Custom User Model

The project uses a **custom User model** (`apps.users.models.User`) as `AUTH_USER_MODEL`. Key features:

- **Email-based authentication** (USERNAME_FIELD = "email")
- **Phone number required** (REQUIRED_FIELDS = ["phone"])
- **Role-based access**: `guest`, `realtor`, `super_admin`, `superuser`
- **Security features**:
  - Failed login attempt tracking with account locking
  - `is_locked` property and `register_failed_attempt()` method
  - Password reset tokens with expiration and attempt limits

**Important**: When creating users programmatically or in tests, always use:
- `User.objects.create_user(email, phone, password)`
- `User.objects.create_superuser(email, phone, password)`

### Domain Apps

**apps.users/**
- Custom User model with role hierarchy (Guest → Realtor → Super Admin → Superuser)
- RealEstateAgency model for grouping realtors
- JWT authentication (djangorestframework-simplejwt)
- PasswordResetToken for secure password recovery
- Phone normalization: `User.normalize_phone(phone)`

**apps.properties/**
- Property model: type (apartment/house/cottage/room/hostel), class (comfort/business/premium), pricing
- PropertyPhoto model with ordering and primary photo logic
- Amenity catalog (M2M with Property)
- Favorite model (User ↔ Property bookmarking)
- Address fields: city, district, address_line, lat/lng
- Check-in/out times, cancellation policy

**apps.bookings/**
- Booking model with comprehensive status workflow:
  - `PENDING` → `CONFIRMED` → `IN_PROGRESS` → `COMPLETED`
  - Cancellation states: `CANCELLED_BY_GUEST`, `CANCELLED_BY_REALTOR`
- **Critical**: `BookingQuerySet.overlapping()` prevents double-booking
- `Booking.create_booking()` class method with atomic transactions
- Review model (1-to-1 with Booking, only after COMPLETED status)
- Validation: min/max stay nights, guest count vs sleeps capacity

### Double-Booking Prevention

The booking system uses multiple layers to prevent conflicts:

1. **Database-level**: `BookingQuerySet.overlapping()` filters by date ranges and active statuses
2. **Transaction atomicity**: `Booking.create_booking()` uses `transaction.atomic()` + `SELECT ... FOR UPDATE`
3. **Status filtering**: Only `PENDING`, `CONFIRMED`, `IN_PROGRESS` bookings block dates

**When implementing booking features:**
- Always use `Booking.create_booking()` class method, never direct `.create()`
- Check overlaps with `.overlapping(property_id, check_in, check_out)` before creating
- Use `select_for_update()` for pessimistic locking in high-concurrency scenarios

### Settings Architecture

- **Base settings**: `config.settings.base` (shared configuration)
- **Dev settings**: `config.settings.dev` (DEBUG=True, local DB)
- **Prod settings**: `config.settings.prod` (production-ready)
- **Environment**: Default is `config.settings.dev` (set in manage.py)
- **Configuration**: Use environment variables via `.env` file (see `.env.example`)

### Authentication & Permissions

- REST Framework with JWT tokens (simplejwt)
- Token endpoints: `/api/v1/auth/` (login, register, token refresh, password reset)
- Role-based permissions: Check `user.role` for access control
  - `guest`: Read-only access (no bookings)
  - `realtor`: Manage own properties and bookings
  - `super_admin`: Manage team realtors (scoped to agency)
  - `superuser`: Full platform access

### URLs Structure

```
/admin/                          # Django admin
/api/v1/auth/                    # Authentication endpoints
/api/v1/properties/              # Property CRUD, search, favorites
/api/v1/bookings/                # Booking creation, management, reviews
```

## Technical Specifications (from TZ)

- **Database**: PostgreSQL with timezone support (Asia/Almaty)
- **Locale**: Russian (ru-ru) primary, Kazakhstan support planned
- **Media**: MinIO (S3-compatible) for photos (max 7MB, 6 photos per property)
- **Payments**: Kaspi Pay integration (MVP), cards/cash planned
- **Background jobs**: Celery + Redis for:
  - Expired booking cleanup (15-min hold period)
  - Notifications (email + Telegram)
  - Analytics generation
- **Booking hold**: 15 minutes to complete payment before auto-cancellation

## Key Business Rules

### Booking Lifecycle

1. User selects dates → creates booking with status `PENDING` (hold)
2. 15-minute timer starts for payment
3. On successful payment → `CONFIRMED` (dates locked)
4. Check-in → `IN_PROGRESS`
5. Check-out → `COMPLETED` (eligible for review)
6. If no payment → Celery job sets to `EXPIRED`, releases dates

### Role Hierarchy

- **Guest**: Browse only, must register to book
- **Realtor**: Manage own properties, see own bookings, access analytics for own properties
- **Super Admin**: Manage realtors in their agency, aggregate analytics for team
- **Superuser**: Platform owner, full access to all data and settings

### Security Requirements

- **Sensitive data encryption**: Property access codes (domofon, apartment, safe) must be encrypted (AES-256)
- **Access logging**: Log all access to encrypted property codes
- **Failed login protection**: After 5 failed attempts, lock account for 15 minutes
- **Password reset**: 6-digit code with 3 attempts, time-limited expiration

## Development Patterns

### Creating New Models

- Use `UUIDField` for primary keys: `id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`
- Add timestamps: `created_at = models.DateTimeField(auto_now_add=True)`, `updated_at = models.DateTimeField(auto_now=True)`
- Use `ForeignKey` with `related_name` for reverse lookups
- Add indexes for frequently queried fields (city, status, dates)

### Writing Tests

- Use `APITestCase` for endpoint tests (see `apps.users.tests.test_auth_api`)
- Test authentication flows, role-based access, and edge cases
- Always test double-booking scenarios for booking-related features
- Use `reverse()` for URL resolution in tests

### Working with Dates

- Always use `timezone.now()` (Django's timezone-aware datetime)
- Date ranges: Use `check_in` (inclusive) and `check_out` (exclusive)
- Booking nights calculation: `(check_out - check_in).days`

## Future Considerations (Stage 2+)

- Multi-city expansion (currently Astana only)
- Hotel/hostel room inventory management
- Dynamic pricing calendar
- Telegram bot integration
- Reviews and ratings system
- Advanced analytics dashboard
- Payouts to property owners

## Critical Files

- **User model**: `apps/users/models.py:74` - Custom user with roles
- **Booking logic**: `apps/bookings/models.py:83` - `Booking.create_booking()` with overlap prevention
- **Settings**: `config/settings/base.py` - Core configuration
- **Celery**: `config/celery.py` - Background task configuration
- **URL routing**: `config/urls.py` - API namespace structure

## Common Pitfalls

1. **Never create bookings directly** - Always use `Booking.create_booking()` to ensure validation and overlap checks
2. **User creation** - Must use `create_user()` manager method (email + phone required)
3. **Settings module** - Set `DJANGO_SETTINGS_MODULE=config.settings.dev` in environment
4. **Migrations** - Run after any model changes, apps are namespaced under `apps.*`
5. **Timezone** - Use `timezone.now()`, not `datetime.now()`
6. **Role checks** - Always verify `user.role` for permission logic, don't rely solely on `is_staff`

## Technical Debt & TODOs

- Property access code encryption not yet implemented (security requirement)
- Analytics, notifications, finances apps are stubs (models.py mostly empty)
- Kaspi Pay integration pending
- Celery periodic tasks for booking expiration not configured
- Telegram bot integration planned but not started
- MinIO/S3 storage not configured (using local MEDIA_ROOT)
