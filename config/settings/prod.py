"""Production settings for ZhilyeGO project.

This module extends the base settings with production specific
configuration. Ensure that sensitive values are provided via
environment variables and that security settings are appropriate for
production use.
"""

from .base import *  # noqa: F401,F403

# Never run with debug enabled in production
DEBUG = False

# Allowed hosts should be defined explicitly via environment variable
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',')

# Configure secure proxies and cookies
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

# Email backend (e.g. SMTP) should be configured via environment variables
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 25))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'false').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
