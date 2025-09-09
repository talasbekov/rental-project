"""
Temporary local settings for demonstration purposes
This file overrides settings.py to use SQLite instead of PostgreSQL
"""

import os
from pathlib import Path
from booking_bot.settings import *

# Override database to use SQLite
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Disable some features that require external services
S3_ENABLED = False
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Disable Redis/Celery for demo
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

print("Using local SQLite database for demonstration")