import structlog
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = structlog.get_logger(__name__)

@csrf_exempt
@require_http_methods(["GET"])
def healthz(request):
    """Health check endpoint for Docker containers"""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        logger.info("healthz.ok", database="connected")
        return JsonResponse({"status": "healthy", "database": "connected"}, status=200)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("healthz.fail", error=str(exc))
        return JsonResponse({"status": "unhealthy", "error": str(exc)}, status=503)
