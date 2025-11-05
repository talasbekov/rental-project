"""ASGI config for ZhilyeGO project.

This module exposes the ASGI application used for serving real‑time
communication (e.g. WebSocket) alongside the traditional HTTP interface.
Refer to the official Django documentation for more information on using
ASGI with Django.
"""

import os
from django.core.asgi import get_asgi_application  # type: ignore

# Use the development settings by default. Production servers should set
# DJANGO_SETTINGS_MODULE accordingly.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

application = get_asgi_application()
