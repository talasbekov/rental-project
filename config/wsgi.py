"""WSGI config for ZhilyeGO project.

This module exposes the WSGI application for use by Django's runserver and
production WSGI servers. It mirrors the default generated file but points
to our settings package.
"""

import os
from django.core.wsgi import get_wsgi_application  # type: ignore

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

application = get_wsgi_application()
