"""Development settings."""

from .base import *  # noqa

DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS += ["django_extensions"]  # type: ignore[name-defined]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
