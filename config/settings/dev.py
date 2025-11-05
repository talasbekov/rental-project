"""Development settings for ZhilyeGO project.

This module extends the base settings with development specific
configuration, such as enabling debug, allowing all hosts and using
console email backend. Do not use these settings in production!
"""

from .base import *  # noqa: F401,F403

# Enable debug mode for development
DEBUG = True

# Allow all hosts in development
ALLOWED_HOSTS = ['*']

# Use console email backend during development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
