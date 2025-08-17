import logging
from django.http import HttpResponseBadRequest
from django.core.exceptions import DisallowedHost

logger = logging.getLogger(__name__)


class FilterHostMiddleware:
    """Middleware для фильтрации подозрительных запросов"""

    def __init__(self, get_response):
        self.get_response = get_response

        # Список подозрительных хостов, которые нужно блокировать
        self.blocked_hosts = {
            'api.ipify.org',
            'www.shadowserver.org',
            'httpbin.org',
            'postman-echo.com',
            'example.com',
            'httpforever.com',
            'requestb.in',
        }

        # Список разрешенных хостов для вашего приложения
        self.allowed_patterns = {
            'jgo.kz',
            'www.jgo.kz',
            'localhost',
            '127.0.0.1',
        }

    def __call__(self, request):
        try:
            host = request.get_host()

            # Проверяем, не является ли хост подозрительным
            if any(blocked in host.lower() for blocked in self.blocked_hosts):
                logger.warning(f"Blocked suspicious host: {host}")
                return HttpResponseBadRequest("Invalid host")

            # Проверяем, является ли это прокси-запросом (HTTP через HTTPS)
            if (hasattr(request, 'META') and
                    request.META.get('REQUEST_METHOD') == 'GET' and
                    request.get_full_path().startswith('http://')):
                logger.warning(f"Blocked proxy request to: {request.get_full_path()}")
                return HttpResponseBadRequest("Proxy requests not allowed")

        except DisallowedHost as e:
            # Логируем и возвращаем 400 вместо 500
            logger.warning(f"DisallowedHost blocked: {e}")
            return HttpResponseBadRequest(f"Host not allowed: {e}")
        except Exception as e:
            logger.error(f"Error in FilterHostMiddleware: {e}")
            # Продолжаем обработку при неожиданных ошибках
            pass

        response = self.get_response(request)
        return response


class CSRFExemptMiddleware:
    """Middleware для исключения CSRF проверки для определенных URL"""

    def __init__(self, get_response):
        self.get_response = get_response

    def process_request(self, request):
        # Список URL паттернов, для которых нужно отключить CSRF
        exempt_urls = [
            r"^telegram/webhook/$",
            r"^whatsapp/webhook/$",
            r"^api/v1/kaspi-webhook/$",
        ]

        import re
        path = request.path_info.lstrip("/")

        for pattern in exempt_urls:
            if re.match(pattern, path):
                setattr(request, "_dont_enforce_csrf_checks", True)
                break

        return None

    def __call__(self, request):
        self.process_request(request)
        response = self.get_response(request)
        return response
