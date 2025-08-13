import hashlib
import hmac
import json
import logging
import re

from django.http import (
    JsonResponse,
    HttpResponseBadRequest,
    HttpResponse,
    HttpResponseForbidden,
)
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from booking_bot.bookings.models import Booking
from booking_bot.telegram_bot.handlers import (
    start_command_handler,
    help_command_handler,
    show_user_bookings,
    message_handler,
    date_input_handler,
)

# Добавляем импорт для обработки фото
from booking_bot.telegram_bot.admin_handlers import handle_photo_upload
from booking_bot.telegram_bot.utils import send_telegram_message
from booking_bot.users.models import UserProfile

logger = logging.getLogger(__name__)


def verify_webhook_signature(request):
    return (
        request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        == settings.WEBHOOK_SECRET
    )


@csrf_exempt
def telegram_webhook(request):
    if not verify_webhook_signature(request):
        return HttpResponseForbidden()
    """Handle incoming updates from Telegram (ReplyKeyboardMarkup only)."""
    if request.method == "GET":
        return HttpResponse("Telegram webhook is running")
    if request.method != "POST":
        return HttpResponseBadRequest("Method not allowed")

    try:
        data = json.loads(request.body)
        logger.debug(f"Received update: {data}")
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook request")
        return HttpResponseBadRequest("Invalid JSON")

    # Обрабатываем только "message"
    if "message" in data:
        message = data["message"]
        chat_id = message["chat"]["id"]
        from_user = message.get("from", {})
        first_name = from_user.get("first_name")
        last_name = from_user.get("last_name")

        # Создаем mock-объекты для совместимости с telegram-бот библиотекой
        class MockPhoto:
            def __init__(self, photo_data):
                self.file_id = photo_data.get("file_id")
                self.file_size = photo_data.get("file_size", 0)
                self.width = photo_data.get("width", 0)
                self.height = photo_data.get("height", 0)

        class MockUpdate:
            def __init__(self, message_data):
                self.message = MockMessage(message_data)

        class MockMessage:
            def __init__(self, message_data):
                self.text = message_data.get("text")
                # Преобразуем photo из списка словарей в список MockPhoto объектов
                photo_data = message_data.get("photo", [])
                self.photo = [MockPhoto(p) for p in photo_data] if photo_data else []

        class MockContext:
            def __init__(self):
                self.bot = MockBot()

        class MockBot:
            def get_file(self, file_id):
                # Простая реализация для получения файла
                class MockFile:
                    def __init__(self, file_id):
                        self.file_id = file_id

                    def download(self, custom_path):
                        import requests

                        bot_token = settings.TELEGRAM_BOT_TOKEN
                        # Получаем путь к файлу
                        get_file_url = (
                            f"https://api.telegram.org/bot{bot_token}/getFile"
                        )
                        response = requests.get(
                            get_file_url, params={"file_id": file_id}
                        )
                        if response.status_code == 200:
                            file_path = response.json()["result"]["file_path"]
                            download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
                            # Скачиваем файл
                            file_response = requests.get(download_url)
                            with open(custom_path, "wb") as f:
                                f.write(file_response.content)

                return MockFile(file_id)

            def send_document(self, *args, **kwargs):
                """
                Мок отправки документа. Принимает позиционные и именованные аргументы:
                (chat_id, document, ...) или chat_id=, document=, filename=, caption=.
                Сохраняет файл во /tmp и пишет путь в логи, чтобы dev/test не падал.
                """
                import io, os, time, logging

                log = logging.getLogger(__name__)

                # распаковка аргументов
                chat_id = kwargs.get("chat_id", args[0] if len(args) > 0 else None)
                document = kwargs.get("document", args[1] if len(args) > 1 else None)
                filename = kwargs.get("filename", None)
                caption = kwargs.get("caption", None)

                saved_path = None
                try:
                    data = None
                    if hasattr(document, "read"):  # file-like (BytesIO, file)
                        pos = document.tell() if hasattr(document, "tell") else None
                        data = document.read()
                        if pos is not None and hasattr(document, "seek"):
                            document.seek(pos)
                        if not filename:
                            filename = getattr(document, "name", None)
                    elif isinstance(document, (bytes, bytearray)):  # сырые байты
                        data = bytes(document)
                    elif isinstance(document, str) and os.path.exists(
                        document
                    ):  # путь к файлу
                        saved_path = document
                        if not filename:
                            filename = os.path.basename(document)

                    if data is not None:
                        if not filename:
                            filename = f"document_{int(time.time())}.bin"
                        saved_path = f"/tmp/{filename}"
                        with open(saved_path, "wb") as f:
                            f.write(data)

                    log.info(
                        "MockBot.send_document(chat_id=%s, filename=%s, caption=%r, saved_path=%s)",
                        chat_id,
                        filename,
                        caption,
                        saved_path,
                    )
                except Exception as e:
                    log.warning("MockBot.send_document error: %s", e)

                return {
                    "ok": True,
                    "result": {"document": {"file_name": filename, "path": saved_path}},
                }

        update_obj = MockUpdate(message)
        context_obj = MockContext()

        # Если есть фото
        if "photo" in message:
            # Обрабатываем фото
            message_handler(chat_id, "", update_obj, context_obj)
        # Если текст пришёл
        elif "text" in message:
            text = message["text"].strip()

            # Сначала — системные команды
            if text.startswith("/start"):
                start_command_handler(chat_id, first_name, last_name)
            elif text.startswith("/help"):
                help_command_handler(chat_id)
            elif text.startswith("/menu"):
                start_command_handler(chat_id, first_name, last_name)
            elif text.startswith("/bookings"):
                show_user_bookings(chat_id, "active")
            elif text.startswith("/history"):
                show_user_bookings(chat_id, "completed")

            # Затем — быстрый ввод дат: формат "DD.MM.YYYY" или кнопки "Сегодня", "Завтра"
            elif (
                re.match(r"^\d{2}\.\d{2}\.\d{4}$", text)
                or text.startswith("Сегодня")
                or text.startswith("Завтра")
            ):
                date_input_handler(chat_id, text)

            # Всё остальное — в message_handler (нажатия на Reply-кнопки и пр.)
            else:
                message_handler(chat_id, text, update_obj, context_obj)

        return JsonResponse({"ok": True})

    # Всё остальное (стики, документы и т.п.) — просто отвечаем OK
    return JsonResponse({"ok": True})


def show_booking_details(chat_id: int, booking_id: int) -> None:
    """Показать подробную информацию о бронировании.

    Выводит информацию о квартире, датах проживания и сумме. Коды
    домофона/сейфа отображаются только после успешной оплаты.
    """
    try:
        profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
    except UserProfile.DoesNotExist:
        send_telegram_message(chat_id, "Профиль не найден.")
        return

    try:
        booking = Booking.objects.select_related(
            "property", "property__owner__profile"
        ).get(id=booking_id, user=profile.user)
    except Booking.DoesNotExist:
        send_telegram_message(chat_id, "Бронирование не найдено.")
        return

    # Общая информация
    property_obj = booking.property
    lines = [f"*Детали бронирования #{booking.id}*\n"]
    lines.append(f"🏠 *{property_obj.name}*")
    lines.append(f"📍 Адрес: {property_obj.address}")
    lines.append(
        f"\n📅 Заезд: {booking.start_date.strftime('%d.%m.%Y')}\n📅 Выезд: {booking.end_date.strftime('%d.%m.%Y')}"
    )
    lines.append(f"💰 Оплачено: {booking.total_price} ₸")

    # Инструкции всегда показываем
    if property_obj.entry_instructions:
        lines.append(f"\n📝 *Инструкции:*\n{property_obj.entry_instructions}")

    # Коды доступа — только если оплата подтверждена
    if booking.status in ("confirmed", "completed"):
        if property_obj.digital_lock_code:
            lines.append(f"\n🔐 Код замка: `{property_obj.digital_lock_code}`")
        elif property_obj.key_safe_code:
            lines.append(f"\n🔑 Код сейфа: `{property_obj.key_safe_code}`")
    else:
        lines.append("\n🔒 Коды доступа станут доступны после подтверждения оплаты.")

    # Контакт владельца
    owner_phone = getattr(property_obj.owner.profile, "phone_number", None)
    if owner_phone:
        lines.append(f"\n📞 Контакт: {owner_phone}")

    text = "\n".join(lines)
    # Кнопка для возврата в меню текущих броней
    keyboard = [[{"text": "◀️ Назад", "callback_data": "main_current"}]]
    send_telegram_message(
        chat_id, text, {"inline_keyboard": keyboard}, parse_mode="Markdown"
    )


def handle_photo_message(chat_id, message):
    """Handle photo uploads (for reviews)"""
    from booking_bot.users.models import UserProfile
    from booking_bot.telegram_bot.utils import send_telegram_message

    try:
        profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
        state_data = profile.telegram_state or {}

        if state_data.get("state") == "awaiting_review_photos":
            # Handle review photo upload
            photos = message.get("photo", [])
            if photos:
                # Get the largest photo
                photo = max(photos, key=lambda p: p.get("file_size", 0))
                file_id = photo.get("file_id")

                # Store file_id in state
                review_photos = state_data.get("review_photos", [])
                review_photos.append(file_id)
                state_data["review_photos"] = review_photos

                if len(review_photos) < 3:
                    send_telegram_message(
                        chat_id,
                        f"Фото {len(review_photos)}/3 загружено. Можете добавить еще или нажать 'Готово'.",
                        {
                            "inline_keyboard": [
                                [
                                    {
                                        "text": "✅ Готово",
                                        "callback_data": "submit_review_with_photos",
                                    }
                                ]
                            ]
                        },
                    )
                else:
                    # Auto-submit after 3 photos
                    submit_review_with_photos(chat_id, profile)

                profile.telegram_state = state_data
                profile.save()
        else:
            send_telegram_message(
                chat_id, "Используйте команду /start для начала работы с ботом."
            )

    except UserProfile.DoesNotExist:
        send_telegram_message(chat_id, "Пользователь не найден. Используйте /start")
    except Exception as e:
        logger.error(f"Error handling photo message: {e}")


def submit_review_with_photos(chat_id, profile):
    """Submit review with uploaded photos"""
    from booking_bot.listings.models import Review, ReviewPhoto
    from booking_bot.bookings.models import Booking
    from booking_bot.telegram_bot.utils import send_telegram_message, get_file_url

    state_data = profile.telegram_state or {}
    booking_id = state_data.get("review_booking_id")
    rating = state_data.get("review_rating")
    text = state_data.get("review_text", "")
    photo_file_ids = state_data.get("review_photos", [])

    try:
        booking = Booking.objects.get(id=booking_id, user=profile.user)

        # Create review
        review = Review.objects.create(
            property=booking.property, user=profile.user, rating=rating, text=text
        )

        # Add photos
        for file_id in photo_file_ids:
            file_url = get_file_url(file_id)
            if file_url:
                ReviewPhoto.objects.create(review=review, image_url=file_url)

        send_telegram_message(chat_id, "Спасибо за ваш отзыв с фотографиями! 📸👍")

        # Clear state
        profile.telegram_state = {}
        profile.save()

    except Exception as e:
        logger.error(f"Error submitting review with photos: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при сохранении отзыва.")
