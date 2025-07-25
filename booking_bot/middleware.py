# booking_bot/middleware.py

import re
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin


class CSRFExemptMiddleware(MiddlewareMixin):
    """Middleware для исключения CSRF проверки для определенных URL"""

    def process_request(self, request):
        # Список URL паттернов, для которых нужно отключить CSRF
        exempt_urls = getattr(settings, 'CSRF_EXEMPT_URLS', [])

        path = request.path_info.lstrip('/')

        for pattern in exempt_urls:
            if re.match(pattern, path):
                setattr(request, '_dont_enforce_csrf_checks', True)
                break

        return None