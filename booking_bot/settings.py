import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

# Optionally load .env file if using python-dotenv
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

BASE_DIR = Path(__file__).resolve().parent.parent

# Helper to get environment variables or raise

def get_env(var_name: str, default=None, required: bool = False):
    value = os.environ.get(var_name, default)
    if required and value in (None, ''):
        raise ImproperlyConfigured(f"Missing required environment variable: {var_name}")
    return value

# SECURITY
SECRET_KEY = 'django-insecure-^18w8^kyktt4q14w%c4tci%w(8po97jj2pd&3(#hv(dyn3hznv'
DEBUG = get_env('DJANGO_DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = get_env('DJANGO_ALLOWED_HOSTS', '').split(',')
APPEND_SLASH = True


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'django_filters',
    'rest_framework',
    'booking_bot.core',
    'booking_bot.users',
    'booking_bot.listings',
    'booking_bot.bookings',
    'booking_bot.payments',
    'booking_bot.whatsapp_bot',
    'booking_bot.telegram_bot',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'booking_bot.middleware.CSRFExemptMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'booking_bot.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'booking_bot.wsgi.application'

# Database configuration (PostgreSQL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': get_env('POSTGRES_DB', required=True),
        'USER': get_env('POSTGRES_USER', required=True),
        'PASSWORD': get_env('POSTGRES_PASSWORD', required=True),
        'HOST': get_env('DB_HOST', 'localhost'),
        'PORT': get_env('DB_PORT', '5432'),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = get_env('DJANGO_TIME_ZONE', 'UTC')
USE_I18N = True
USE_TZ = True

# Static and media files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework_simplejwt.authentication.JWTAuthentication'],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# Simple JWT
SIMPLE_JWT = {
    # Customize token lifetimes as needed
}

# Bots and external APIs
TELEGRAM_BOT_TOKEN = get_env('TELEGRAM_BOT_TOKEN', required=True)
BOT_SERVICE_USERNAME = get_env('BOT_SERVICE_USERNAME', '')
# WHATSAPP_ACCESS_TOKEN = get_env('WHATSAPP_ACCESS_TOKEN', '')
# KASPI_API_KEY = get_env('KASPI_API_KEY', '')
# KASPI_MERCHANT_ID = get_env('KASPI_MERCHANT_ID', '')
WEBHOOK_SECRET = get_env('WEBHOOK_SECRET', '')

# Encryption key for custom fields
# ENCRYPTION_KEY = get_env('ENCRYPTION_KEY', required=True)

# Domain and URLs\NGRK
NGROK_URL = get_env('NGROK_URL', '')
DOMAIN = NGROK_URL
SITE_URL = NGROK_URL
API_BASE = f"{NGROK_URL}/api/v1"

# CSRF settings
raw_csrf = get_env('CSRF_TRUSTED_ORIGINS', default='')
CSRF_TRUSTED_ORIGINS = [host.strip() for host in raw_csrf.split(',') if host.strip()]
CSRF_EXEMPT_URLS = [r'^/telegram/webhook/$']

# Security hardening
# SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# File upload limits
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module} {message}', 'style': '{'},
        'simple': {'format': '{levelname} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple', 'level': 'INFO'},
    },
    'root': {'handlers': ['console'], 'level': 'WARNING'},
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'booking_bot': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
