"""
Initialize Django application and Celery app.

This module sets the default Celery app for 'django' and ensures tasks are
autodiscovered. Import celery_app at module level so that it is created
when Django starts.
"""
from .celery import app as celery_app

__all__ = ('celery_app',)