"""
Celery application for booking_bot project.

This module defines the Celery instance used throughout the project. It reads
configuration from Django settings under the `CELERY_` namespace and
autodiscover tasks from installed apps. The beat schedule itself is defined
in `settings.py`.
"""

import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "booking_bot.settings")

app = Celery("booking_bot")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    """A simple debug task to test Celery."""
    print(f"Request: {self.request!r}")
