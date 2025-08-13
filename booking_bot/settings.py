import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

# Optionally load .env file if using python-dotenv
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Celery beat schedule helpers
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

# Helper to get environment variables or raise


def get_env(var_name: str, default=None, required: bool = False):
    value = os.environ.get(var_name, default)
    if required and value in (None, ""):
        raise ImproperlyConfigured(f"Missing required environment variable: {var_name}")
    return value


# SECURITY
SECRET_KEY = get_env("DJANGO_SECRET_KEY", required=True)
DEBUG = get_env("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = get_env("DJANGO_ALLOWED_HOSTS", "").split(",")
APPEND_SLASH = True


# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_filters",
    "rest_framework",
    "booking_bot.core",
    "booking_bot.users",
    "booking_bot.listings",
    "booking_bot.bookings",
    "booking_bot.payments",
    "booking_bot.telegram_bot",
    "booking_bot.notifications",
    "booking_bot.whatsapp_bot.apps.WhatsAppBotConfig",
    "django_cryptography",
    "django_celery_beat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "booking_bot.middleware.CSRFExemptMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "booking_bot.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "booking_bot.wsgi.application"

# Database configuration (PostgreSQL)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": get_env("POSTGRES_DB", required=True),
        "USER": get_env("POSTGRES_USER", required=True),
        "PASSWORD": get_env("POSTGRES_PASSWORD", required=True),
        "HOST": get_env("DB_HOST", "localhost"),
        "PORT": get_env("DB_PORT", "5432"),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = get_env("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True

# Для работы за reverse proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_TZ = True

# Static and media files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Bots and external APIs
TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN", required=True)
BOT_SERVICE_USERNAME = get_env("BOT_SERVICE_USERNAME", "")
WEBHOOK_SECRET = get_env("WEBHOOK_SECRET", "")

# WhatsApp Business API Settings
WHATSAPP_ACCESS_TOKEN = get_env("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_PHONE_NUMBER_ID = get_env("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_BUSINESS_ACCOUNT_ID = get_env("WHATSAPP_BUSINESS_ACCOUNT_ID", default="")
WHATSAPP_VERIFY_TOKEN = get_env(
    "WHATSAPP_VERIFY_TOKEN", default="your-verify-token-here"
)

# Encryption key for custom fields
# ENCRYPTION_KEY = get_env('ENCRYPTION_KEY', required=True)

# Domain configuration
# Use DJANGO_DOMAIN environment variable to configure the domain without relying on ngrok.
# In development, default to localhost. SITE_URL points to the same domain.
DOMAIN = get_env("DJANGO_DOMAIN", "http://localhost:8000")
SITE_URL = DOMAIN
API_BASE = f"{DOMAIN}/api/v1"

# Kaspi Payment Gateway Settings
KASPI_API_KEY = get_env("KASPI_API_KEY", "")
KASPI_MERCHANT_ID = get_env("KASPI_MERCHANT_ID", "")
KASPI_SECRET_KEY = get_env("KASPI_SECRET_KEY", "")
KASPI_API_BASE_URL = get_env("KASPI_API_BASE_URL", "https://api.kaspi.kz/v2/")

# Убрать предупреждения про AutoField
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Payment settings
PAYMENT_SUCCESS_URL = f"{SITE_URL}/payments/success/"
PAYMENT_FAIL_URL = f"{SITE_URL}/payments/fail/"
PAYMENT_TIMEOUT_MINUTES = 15

# Для разработки - автоматическое подтверждение платежей
AUTO_CONFIRM_PAYMENTS = DEBUG  # True только в DEBUG режиме

# CSRF settings
raw_csrf = get_env("CSRF_TRUSTED_ORIGINS", default="")
CSRF_TRUSTED_ORIGINS = [host.strip() for host in raw_csrf.split(",") if host.strip()]
CSRF_EXEMPT_URLS = [r"^/telegram/webhook/$"]

# Security hardening
# SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# File upload limits
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Celery configuration
# Define broker and result backend from environment or default to Redis.
CELERY_BROKER_URL = get_env("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = get_env("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"

# S3/MinIO настройки
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "zhiliego-photos")
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")

# Для MinIO (self-hosted S3)
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)  # например: http://minio:9000

# CloudFront CDN (опционально)
AWS_CLOUDFRONT_DOMAIN = os.environ.get("AWS_CLOUDFRONT_DOMAIN", None)

# Настройки оптимизации фотографий
PHOTO_MAX_SIZE = 5 * 1024 * 1024  # 5 МБ
PHOTO_MAX_DIMENSION = 1920  # Максимальная ширина/высота
PHOTO_THUMBNAIL_SIZE = (400, 300)  # Размер миниатюры

# Кэширование
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": "max-age=86400",  # 1 день
}

# Для локальной разработки можно использовать MinIO в Docker
if DEBUG:
    S3_ENDPOINT_URL = "http://localhost:9000"
    AWS_ACCESS_KEY_ID = "minioadmin"
    AWS_SECRET_ACCESS_KEY = "minioadmin"

# Celery beat schedule example tasks. Adjust schedules as needed.
CELERY_BEAT_SCHEDULE = {
    # Обработка уведомлений
    "process-notifications": {
        "task": "booking_bot.notifications.tasks.process_notification_queue",
        "schedule": crontab(minute="*/1"),  # каждую минуту
    },
    # Проверка истекших бронирований
    "check-expired-bookings": {
        "task": "booking_bot.bookings.tasks.check_all_expired_bookings",
        "schedule": crontab(minute="*/5"),  # каждые 5 минут
    },
    # Актуализация статусов бронирований
    "update-booking-statuses": {
        "task": "booking_bot.bookings.tasks.update_booking_statuses",
        "schedule": crontab(hour=0, minute=1),  # ежедневно в 00:01
    },
    # Напоминания о заезде
    "send-checkin-reminders": {
        "task": "booking_bot.bookings.tasks.send_checkin_reminder",
        "schedule": crontab(hour=10, minute=0),  # ежедневно в 10:00
    },
    # Мониторинг загрузки
    "monitor-occupancy": {
        "task": "booking_bot.bookings.tasks.check_low_demand_properties",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),  # понедельник 9:00
    },
    # Анализ KO-фактора гостей
    "analyze-ko-factor": {
        "task": "booking_bot.bookings.tasks.analyze_guest_ko_factor",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),  # воскресенье 02:00
    },
    # Ежемесячный отчет
    "monthly-report": {
        "task": "booking_bot.bookings.tasks.generate_monthly_report",
        "schedule": crontab(hour=9, minute=0, day_of_month=1),  # 1-го числа в 09:00
    },
    # Проверка необходимости обновления фото/цен
    "check-updates-needed": {
        "task": "booking_bot.bookings.tasks.check_property_updates_needed",
        "schedule": crontab(hour=11, minute=0, day_of_week=3),  # среда 11:00
    },
    # Расширение календаря на будущее
    "extend-calendar": {
        "task": "booking_bot.listings.tasks.extend_calendar_forward",
        "schedule": crontab(hour=3, minute=0, day_of_week=1),  # понедельник 03:00
    },
    # Очистка старых записей календаря
    "cleanup-calendar": {
        "task": "booking_bot.listings.tasks.cleanup_old_calendar_days",
        "schedule": crontab(hour=4, minute=0, day_of_month=1),  # 1-го числа в 04:00
    },
    # Напоминание о заезде за день
    "checkin-reminder": {
        "task": "booking_bot.bookings.tasks.send_checkin_reminder",
        "schedule": crontab(hour=10, minute=0),  # каждый день в 10:00
    },
    # Запрос отзыва после выезда
    "review-request": {
        "task": "booking_bot.bookings.tasks.send_review_request",
        "schedule": crontab(hour=12, minute=0),  # каждый день в 12:00
    },
    # Предложение продления за 2 дня до выезда
    "extend-reminder": {
        "task": "booking_bot.bookings.tasks.send_extend_reminder",
        "schedule": crontab(hour=15, minute=0),  # каждый день в 15:00
    },
}

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {module} {message}", "style": "{"},
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "level": "INFO",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "booking_bot": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# В разделе LOGGING добавьте логгер для платежей
LOGGING["loggers"]["booking_bot.payments"] = {
    "handlers": ["console"],
    "level": "INFO",
    "propagate": False,
}
