"""Top-level package for Django configuration.

This package exposes application configuration for the ZhilyeGO platform. It
contains settings modules for different environments and entry points
for WSGI and ASGI.
"""

# Import the Celery application as soon as Django starts. Without this
# the shared task registry will not be populated.
from .celery import app as celery_app  # noqa: F401
