"""Webhook views for Telegram bot."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from telegram import Update

from .bot import build_application

logger = logging.getLogger(__name__)

# Global application instance (initialized once)
_application = None


def get_application():
    """Get or create the Telegram application instance."""
    global _application
    if _application is None:
        _application = build_application()
        logger.info("Telegram bot application initialized for webhook mode")
    return _application


@csrf_exempt
@require_POST
async def telegram_webhook(request: HttpRequest) -> HttpResponse:
    """
    Handle incoming webhook requests from Telegram.

    This endpoint receives POST requests from Telegram servers containing
    updates (messages, callbacks, etc.) and processes them asynchronously.
    """
    try:
        # Parse JSON payload
        data: dict[str, Any] = json.loads(request.body.decode('utf-8'))
        logger.debug(f"Received webhook data: {data}")

        # Create Update object from incoming data
        update = Update.de_json(data, get_application().bot)

        if update:
            # Process the update asynchronously
            application = get_application()
            await application.process_update(update)

            logger.info(f"Processed update: {update.update_id}")
            return JsonResponse({"status": "ok"}, status=200)
        else:
            logger.warning("Received invalid update data")
            return JsonResponse({"status": "error", "message": "Invalid update"}, status=400)

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
async def telegram_health(request: HttpRequest) -> HttpResponse:
    """Health check endpoint for the Telegram bot webhook."""
    try:
        application = get_application()
        bot_info = await application.bot.get_me()

        return JsonResponse({
            "status": "healthy",
            "bot": {
                "id": bot_info.id,
                "username": bot_info.username,
                "name": bot_info.first_name,
            }
        }, status=200)
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return JsonResponse({
            "status": "unhealthy",
            "error": str(e)
        }, status=500)
