import json
import logging
import re
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django_ratelimit.decorators import ratelimit

from booking_bot.whatsapp_bot.handlers import (
    start_command_handler,
    help_command_handler,
    show_user_bookings,
    message_handler,
    handle_button_click,
)
from booking_bot.whatsapp_bot.admin_handlers import (
    handle_photo_upload,
    show_admin_panel,
    show_admin_properties,
    show_detailed_statistics,
    show_extended_statistics,
    export_statistics_csv,
    handle_add_property_start,
)
from booking_bot.users.models import UserProfile
from .utils import mark_message_as_read

logger = logging.getLogger(__name__)


@csrf_exempt
def whatsapp_verify_webhook(request):
    """Верификация webhook для WhatsApp Business API"""
    if request.method == "GET":
        # Получаем параметры верификации
        verify_token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        # Проверяем токен
        if verify_token == settings.WHATSAPP_VERIFY_TOKEN:
            logger.info("WhatsApp webhook verified successfully")
            return HttpResponse(challenge)
        else:
            logger.error("Invalid verify token")
            return HttpResponseBadRequest("Invalid verify token")

    return HttpResponseBadRequest("Only GET allowed for verification")


@csrf_exempt
@ratelimit(key='ip', rate='100/m', method='POST')
def whatsapp_webhook(request):
    # Check rate limit
    if getattr(request, 'limited', False):
        logger.warning(f"Rate limit exceeded for IP: {request.META.get('REMOTE_ADDR')}")
        return JsonResponse({"error": "Rate limit exceeded"}, status=429)
    """Обработка входящих сообщений от WhatsApp Business API"""
    if request.method == "GET":
        return HttpResponse("WhatsApp webhook is running")

    if request.method != "POST":
        return HttpResponseBadRequest("Method not allowed")

    try:
        data = json.loads(request.body)
        logger.debug(f"Received WhatsApp webhook: {data}")
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook request")
        return HttpResponseBadRequest("Invalid JSON")

    # Обрабатываем входящие сообщения
    try:
        entry = data.get("entry", [])
        if not entry:
            return JsonResponse({"status": "ok"})

        for item in entry:
            changes = item.get("changes", [])
            for change in changes:
                value = change.get("value", {})

                # Обрабатываем только сообщения
                messages = value.get("messages", [])
                for message in messages:
                    process_whatsapp_message(message, value)

        return JsonResponse({"status": "ok"})

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)})


def process_whatsapp_message(message, value):
    """Обработка одного сообщения WhatsApp"""
    try:
        # Получаем данные отправителя
        phone_number = message.get("from")
        message_id = message.get("id")

        # Отмечаем сообщение как прочитанное
        mark_message_as_read(message_id)

        # Получаем контакты (если есть)
        contacts = value.get("contacts", [])
        contact_name = None
        if contacts:
            contact = contacts[0]
            profile = contact.get("profile", {})
            contact_name = profile.get("name")

        # Определяем тип сообщения
        message_type = message.get("type")

        # Структура для передачи в обработчик
        message_data = {"type": message_type, "id": message_id}

        # Обрабатываем текстовые сообщения
        if message_type == "text":
            text = message.get("text", {}).get("body", "").strip()

            # Проверяем системные команды
            if text.lower() in ["/start", "start", "старт", "начать", "привет"]:
                start_command_handler(phone_number, contact_name)
                return

            if text.lower() in ["/help", "help", "помощь"]:
                help_command_handler(phone_number)
                return

            if text.lower() in ["мои бронирования", "брони", "bookings"]:
                show_user_bookings(phone_number, "completed")
                return

            if text.lower() in ["статус", "текущая бронь", "status"]:
                show_user_bookings(phone_number, "active")
                return

            # Проверяем админские команды
            profile = UserProfile.objects.filter(whatsapp_phone=phone_number).first()
            if profile and profile.role in ("admin", "super_admin", "super_user"):
                if text.lower() in ["админ", "admin", "панель"]:
                    show_admin_panel(phone_number)
                    return

                if text.lower() in ["статистика", "stats"]:
                    show_detailed_statistics(phone_number)
                    return

                if text.lower() in ["мои квартиры", "квартиры"]:
                    show_admin_properties(phone_number)
                    return

            # Передаем в основной обработчик
            message_handler(phone_number, text, message_data)

        # Обрабатываем интерактивные ответы (нажатия на кнопки)
        elif message_type == "interactive":
            interactive = message.get("interactive", {})
            message_data["interactive"] = interactive

            # Получаем ID нажатой кнопки
            button_reply = interactive.get("button_reply")
            list_reply = interactive.get("list_reply")

            if button_reply:
                button_id = button_reply.get("id")
                button_text = button_reply.get("title")

                # Обрабатываем специальные кнопки
                profile = UserProfile.objects.filter(
                    whatsapp_phone=phone_number
                ).first()
                if not profile:
                    profile = _get_or_create_local_profile(phone_number)

                # Обрабатываем нажатие кнопки
                handle_button_click(phone_number, button_id, profile)

            elif list_reply:
                list_id = list_reply.get("id")
                list_title = list_reply.get("title")

                # Аналогично обрабатываем выбор из списка
                profile = UserProfile.objects.filter(
                    whatsapp_phone=phone_number
                ).first()
                if not profile:
                    profile = _get_or_create_local_profile(phone_number)

                handle_button_click(phone_number, list_id, profile)

        # Обрабатываем изображения
        elif message_type == "image":
            image = message.get("image", {})
            message_data["image"] = image

            # Проверяем, находимся ли мы в режиме загрузки фото для квартиры
            profile = UserProfile.objects.filter(whatsapp_phone=phone_number).first()
            if profile:
                handle_photo_upload(phone_number, message_data)
            else:
                message_handler(phone_number, "", message_data)

        # Обрабатываем локацию
        elif message_type == "location":
            location = message.get("location", {})
            lat = location.get("latitude")
            lon = location.get("longitude")
            name = location.get("name")
            address = location.get("address")

            text = f"Получена локация: {name or address or f'{lat}, {lon}'}"
            message_handler(phone_number, text, message_data)

        # Обрабатываем документы
        elif message_type == "document":
            document = message.get("document", {})
            filename = document.get("filename", "document")

            text = f"Получен документ: {filename}"
            message_handler(phone_number, text, message_data)

        # Другие типы сообщений
        else:
            logger.warning(f"Unsupported message type: {message_type}")
            message_handler(
                phone_number,
                "Извините, этот тип сообщений не поддерживается. Используйте текст или кнопки.",
                message_data,
            )

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)


def _get_or_create_local_profile(phone_number):
    """Получить или создать профиль пользователя"""
    from booking_bot.whatsapp_bot.constants import _get_or_create_local_profile

    return _get_or_create_local_profile(phone_number)
