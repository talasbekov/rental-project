import json
import logging
import requests
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from booking_bot.telegram_bot.handlers import (
    start_command_handler, help_command_handler, callback_query_handler, date_input_handler
)


logger = logging.getLogger(__name__)
BOT_BASE = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"


def _answer_callback(query_id):
    try:
        requests.post(f"{BOT_BASE}/answerCallbackQuery", json={"callback_query_id": query_id}, timeout=5)
    except Exception:
        logger.exception("Failed to answer callback")


@csrf_exempt
def telegram_webhook(request):
    if request.method == 'GET':
        return HttpResponse("Webhook up and running")
    if request.method != "POST":
        return HttpResponseBadRequest()
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest()

    # callback_query
    if "callback_query" in data:
        cq = data["callback_query"]
        _answer_callback(cq["id"])
        chat_id = cq["message"]["chat"]["id"]
        msg_id = cq["message"]["message_id"]
        callback_query_handler(chat_id, cq.get("data", ""), msg_id)
        return JsonResponse({"ok": True})

    # message
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()
        if text.startswith("/start"):
            start_command_handler(chat_id)
        elif text.startswith("/menu"):
            start_command_handler(chat_id)
        elif text.startswith("/help"):
            help_command_handler(chat_id)
            help_command_handler(chat_id)
        elif text.startswith("/help"):
            help_command_handler(chat_id)
        else:
            # возможно ввод даты
            date_input_handler(chat_id, text)
        return JsonResponse({"ok": True})

    return JsonResponse({"ok": True})
