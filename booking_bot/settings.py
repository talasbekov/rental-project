import os
from pathlib import Path

import structlog
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

# ИСПРАВЛЕНИЕ: Более безопасная настройка ALLOWED_HOSTS
allowed_hosts_env = get_env("DJANGO_ALLOWED_HOSTS", "")
if allowed_hosts_env:
    ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_env.split(",") if host.strip()]
else:
    # По умолчанию для разработки используем явный список доверенных хостов
    if DEBUG:
        ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
    else:
        ALLOWED_HOSTS = ["jgo.kz", "www.jgo.kz"]  # В продакшене только ваши домены

APPEND_SLASH = True

# Добавляем настройку для фильтрации подозрительных запросов
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True


# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_prometheus",
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
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "booking_bot.middleware.FilterHostMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "booking_bot.middleware.CSRFExemptMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
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
        "ENGINE": "django_prometheus.db.backends.postgresql",
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
ENCRYPTION_KEY = get_env("ENCRYPTION_KEY", required=True)

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
KASPI_REFUND_URL = get_env(
    "KASPI_REFUND_URL",
    f"{KASPI_API_BASE_URL.rstrip('/')}/payments/refund",
)

# Убрать предупреждения про AutoField
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Payment settings
PAYMENT_SUCCESS_URL = f"{SITE_URL}/payments/success/"
PAYMENT_FAIL_URL = f"{SITE_URL}/payments/fail/"
PAYMENT_TIMEOUT_MINUTES = 15

# Управление авто-подтверждением платежей (эмуляция Kaspi)
AUTO_CONFIRM_PAYMENTS = (
    get_env("AUTO_CONFIRM_PAYMENTS", "true").lower() == "true"
)

# БЕЗОПАСНОСТЬ: Запретить AUTO_CONFIRM_PAYMENTS в production (Claude Code Этап 31)
if not DEBUG and AUTO_CONFIRM_PAYMENTS:
    raise ImproperlyConfigured(
        "CRITICAL SECURITY: AUTO_CONFIRM_PAYMENTS must be disabled in production mode. "
        "Set AUTO_CONFIRM_PAYMENTS=false in .env or enable DEBUG mode for testing."
    )

# Альтернативные способы оплаты
MANUAL_PAYMENT_ENABLED = get_env("MANUAL_PAYMENT_ENABLED", "true").lower() == "true"
MANUAL_PAYMENT_INSTRUCTIONS = get_env(
    "MANUAL_PAYMENT_INSTRUCTIONS",
    "Наш оператор свяжется с вами для выставления счёта и подтверждения оплаты.",
)
MANUAL_PAYMENT_HOLD_MINUTES = int(get_env("MANUAL_PAYMENT_HOLD_MINUTES", "180"))

# CSRF settings
raw_csrf = get_env("CSRF_TRUSTED_ORIGINS", default="")
CSRF_TRUSTED_ORIGINS = [host.strip() for host in raw_csrf.split(",") if host.strip()]
CSRF_EXEMPT_URLS = [r"^/telegram/webhook/$"]

# Security hardening
# SECURE_SSL_REDIRECT = True
# Security hardening
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if DEBUG:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
    # SECURE_SSL_REDIRECT = False  # при желании
else:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = get_env("SECURE_SSL_REDIRECT", "True").lower() == "true"


# File upload limits
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Celery / Redis
REDIS_HOST = get_env("REDIS_HOST", "redis")
REDIS_PASSWORD = get_env("REDIS_PASSWORD", "")
_redis_auth = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""

CELERY_BROKER_URL = get_env("CELERY_BROKER_URL", f"redis://{_redis_auth}{REDIS_HOST}:6379/0")
CELERY_RESULT_BACKEND = get_env("CELERY_RESULT_BACKEND", f"redis://{_redis_auth}{REDIS_HOST}:6379/1")

# Django cache configuration
DEFAULT_CACHE_URL = get_env("CACHE_URL", get_env("REDIS_CACHE_URL", ""))

if DEFAULT_CACHE_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": DEFAULT_CACHE_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "booking-bot-cache",
        }
    }

SEARCH_CACHE_ENABLED = get_env("SEARCH_CACHE_ENABLED", "true").lower() == "true"
SEARCH_CACHE_TIMEOUT = int(get_env("SEARCH_CACHE_TIMEOUT", "120"))
SEARCH_CACHE_PREFIX = get_env("SEARCH_CACHE_PREFIX", "search:properties")

CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"


# S3/MinIO настройки
S3_ENABLED = get_env("S3_ENABLED", "true").lower() == "true"

# ИСПРАВЛЕНИЕ: Используем правильные адреса для разных окружений
if DEBUG:
    # В режиме разработки
    S3_ENDPOINT_URL = get_env("S3_ENDPOINT_URL", "http://minio:9000")  # Внутренний адрес для Docker
    S3_PUBLIC_BASE = get_env("S3_PUBLIC_BASE", "http://localhost:9000/jgo-photos")  # Внешний адрес для Telegram
else:
    # В продакшене
    S3_ENDPOINT_URL = get_env("S3_ENDPOINT_URL", "http://minio:9000")
    S3_PUBLIC_BASE = get_env("S3_PUBLIC_BASE", "https://cdn.jgo.kz")  # Ваш CDN

S3_ACCESS_KEY = get_env("S3_ACCESS_KEY", get_env("AWS_ACCESS_KEY_ID", "minio_access_key"))
S3_SECRET_KEY = get_env("S3_SECRET_KEY", get_env("AWS_SECRET_ACCESS_KEY", "minio_secret_key"))
S3_BUCKET_NAME = get_env("S3_BUCKET_NAME", get_env("AWS_STORAGE_BUCKET_NAME", "jgo-photos"))
S3_REGION = get_env("S3_REGION", get_env("AWS_S3_REGION_NAME", "us-east-1"))
S3_ADDRESSING_STYLE = get_env("S3_ADDRESSING_STYLE", "path")
S3_USE_SSL = get_env("S3_USE_SSL", "false").lower() == "true"

# CloudFront CDN (опционально)
AWS_CLOUDFRONT_DOMAIN = get_env("AWS_CLOUDFRONT_DOMAIN", None)

# Включаем наш кастомный сторедж по умолчанию (если используете его глобально)
if S3_ENABLED and S3_ENDPOINT_URL:
    DEFAULT_FILE_STORAGE = "booking_bot.core.storage.S3PhotoStorage"

# Настройки оптимизации фотографий
PHOTO_MAX_SIZE = 5 * 1024 * 1024  # 5 МБ
PHOTO_MAX_DIMENSION = 1920  # Максимальная ширина/высота
PHOTO_THUMBNAIL_SIZE = (400, 300)  # Размер миниатюры

# Кэширование
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": "max-age=86400",  # 1 день
}

# Celery beat schedule example tasks. Adjust schedules as needed.
CELERY_BEAT_SCHEDULE = {
    "review-request-enqueue-daily": {
        "task": "booking_bot.bookings.tasks.enqueue_daily_review_requests",
        "schedule": crontab(hour=12, minute=0),  # күн сайын 12:00
        "options": {"queue": "default"},
    },
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
    "review-reminder": {
        "task": "booking_bot.bookings.tasks.send_review_reminder",
        "schedule": crontab(hour=12, minute=0),  # каждый день в 12:00
    },
    # Предложение продления за 2 дня до выезда
    "extend-reminder": {
        "task": "booking_bot.bookings.tasks.send_extend_reminder",
        "schedule": crontab(hour=15, minute=0),  # каждый день в 15:00
    },
}

# Логирование подозрительных запросов
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "structlog.stdlib.ProcessorFormatter",
            "processor": structlog.processors.JSONRenderer(),
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "level": "INFO",
        }
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "booking_bot": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.security.DisallowedHost": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "booking_bot.payments": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

PROMETHEUS_EXPORT_MIGRATIONS = False
