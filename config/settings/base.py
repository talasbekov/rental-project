"""Base settings shared across environments for ЖильеGO."""

from pathlib import Path
from datetime import timedelta
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


SECRET_KEY = env("DJANGO_SECRET_KEY", "changeme-insecure")
DEBUG = False

ALLOWED_HOSTS: list[str] = env("DJANGO_ALLOWED_HOSTS", "").split(",") if env("DJANGO_ALLOWED_HOSTS") else []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "django_celery_beat",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    # Our apps
    "shared",  # Shared kernel
    "apps.users",
    "apps.properties",
    "apps.bookings",
    "apps.analytics",
    "apps.notifications",
    "apps.finances",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # CORS
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "zhilyego"),
        "USER": env("POSTGRES_USER", "zhilyego"),
        "PASSWORD": env("POSTGRES_PASSWORD", "zhilyego"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Asia/Almaty"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://redis:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"

# CORS Settings
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS", "").split(",") if env("CORS_ALLOWED_ORIGINS") else []
CORS_ALLOW_CREDENTIALS = True

# API Documentation
SPECTACULAR_SETTINGS = {
    "TITLE": "ЖильеGO API",
    "DESCRIPTION": "API for ЖильеGO rental platform",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# Encryption (for sensitive data like property access codes)
ENCRYPTION_KEY = env("ENCRYPTION_KEY", "")

# MinIO / S3 Storage
AWS_ACCESS_KEY_ID = env("MINIO_ACCESS_KEY", "")
AWS_SECRET_ACCESS_KEY = env("MINIO_SECRET_KEY", "")
AWS_STORAGE_BUCKET_NAME = env("MINIO_BUCKET_NAME", "zhilyego")
AWS_S3_ENDPOINT_URL = env("MINIO_ENDPOINT", "http://minio:9000")
AWS_S3_CUSTOM_DOMAIN = None
AWS_DEFAULT_ACL = "public-read"
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": "max-age=86400",
}

# Telegram Bot
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", "")

# Kaspi Pay
KASPI_PAY_API_URL = env("KASPI_PAY_API_URL", "https://api.kaspi.kz")
KASPI_PAY_MERCHANT_ID = env("KASPI_PAY_MERCHANT_ID", "")
KASPI_PAY_SECRET_KEY = env("KASPI_PAY_SECRET_KEY", "")

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": env("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "shared": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
