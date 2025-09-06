# booking_bot/telegram_bot/user_review_handlers.py

import logging
import html
from datetime import date, datetime
from django.utils import timezone
from telegram import ReplyKeyboardMarkup, KeyboardButton

from .constants import _get_profile, log_handler
from .utils import send_telegram_message
from .. import settings
from booking_bot.listings.models import Property, Review, ReviewPhoto
from booking_bot.bookings.models import Booking

logger = logging.getLogger(__name__)


@log_handler
def handle_review_booking_command(chat_id, booking_id):
    """Обработчик команды /review_<booking_id> - создание отзыва"""
    profile = _get_profile(chat_id)

    try:
        booking = Booking.objects.get(
            id=booking_id,
            user=profile.user,
            status="completed"
        )

        # Проверяем, нет ли уже отзыва для этого конкретного бронирования
        existing_review = Review.objects.filter(
            property=booking.property,
            user=profile.user,
            booking_id=booking.id
        ).first()

        if existing_review:
            # Предлагаем редактировать существующий отзыв
            text = (
                f"📝 У вас уже есть отзыв на эту квартиру.\n\n"
                f"⭐ Оценка: {'⭐' * existing_review.rating}\n"
                f"💬 Текст: {existing_review.text[:100] if existing_review.text else 'Без комментария'}...\n\n"
                f"Хотите изменить отзыв?"
            )

            keyboard = [
                [KeyboardButton("✏️ Редактировать")],
                [KeyboardButton("❌ Отмена")]
            ]

            profile.telegram_state = {
                "state": "confirm_edit_review",
                "review_booking_id": booking_id,
                "existing_review_id": existing_review.id
            }
            profile.save()

            send_telegram_message(
                chat_id,
                text,
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
            )
            return

        # Начинаем процесс создания отзыва
        start_review_creation(chat_id, booking)

    except Booking.DoesNotExist:
        send_telegram_message(
            chat_id,
            "❌ Бронирование не найдено или еще не завершено.\n"
            "Оценить можно только завершенные бронирования."
        )


@log_handler
def handle_edit_review_command(chat_id, booking_id):
    """Обработчик команды /edit_review_<booking_id> - редактирование отзыва"""
    profile = _get_profile(chat_id)

    try:
        booking = Booking.objects.get(
            id=booking_id,
            user=profile.user,
            status="completed"
        )

        existing_review = Review.objects.filter(
            property=booking.property,
            user=profile.user,
            booking_id=booking.id
        ).first()

        if not existing_review:
            send_telegram_message(
                chat_id,
                f"❌ Отзыв не найден.\n"
                f"Для создания нового отзыва используйте: /review_{booking_id}"
            )
            return

        # Начинаем процесс редактирования
        start_review_editing(chat_id, booking, existing_review)

    except Booking.DoesNotExist:
        send_telegram_message(
            chat_id,
            "❌ Бронирование не найдено"
        )


@log_handler
def start_review_creation(chat_id, booking):
    """Начать создание нового отзыва"""
    profile = _get_profile(chat_id)

    # Сохраняем состояние
    profile.telegram_state = {
        "state": "user_review_rating",
        "review_booking_id": booking.id,
        "review_property_id": booking.property.id,
        "review_mode": "create"
    }
    profile.save()

    text = (
        f"⭐ *Оцените квартиру*\n\n"
        f"🏠 {booking.property.name}\n"
        f"📅 Ваше пребывание: {booking.start_date.strftime('%d.%m.%Y')} - "
        f"{booking.end_date.strftime('%d.%m.%Y')}\n\n"
        "Поставьте оценку от 1 до 5 звезд:"
    )

    keyboard = [
        [KeyboardButton("⭐"), KeyboardButton("⭐⭐"), KeyboardButton("⭐⭐⭐")],
        [KeyboardButton("⭐⭐⭐⭐"), KeyboardButton("⭐⭐⭐⭐⭐")],
        [KeyboardButton("❌ Отмена")]
    ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
    )


@log_handler
def start_review_editing(chat_id, booking, existing_review):
    """Начать редактирование существующего отзыва"""
    profile = _get_profile(chat_id)

    # Сохраняем состояние с ID существующего отзыва
    profile.telegram_state = {
        "state": "user_review_rating",
        "review_booking_id": booking.id,
        "review_property_id": booking.property.id,
        "review_mode": "edit",
        "existing_review_id": existing_review.id
    }
    profile.save()

    current_stars = "⭐" * existing_review.rating

    text = (
        f"✏️ *Редактирование отзыва*\n\n"
        f"🏠 {booking.property.name}\n"
        f"📅 Ваше пребывание: {booking.start_date.strftime('%d.%m.%Y')} - "
        f"{booking.end_date.strftime('%d.%m.%Y')}\n\n"
        f"Текущая оценка: {current_stars} ({existing_review.rating}/5)\n"
        f"Текущий отзыв: {existing_review.text[:100] if existing_review.text else 'Без комментария'}...\n\n"
        "Поставьте новую оценку:"
    )

    keyboard = [
        [KeyboardButton("⭐"), KeyboardButton("⭐⭐"), KeyboardButton("⭐⭐⭐")],
        [KeyboardButton("⭐⭐⭐⭐"), KeyboardButton("⭐⭐⭐⭐⭐")],
        [KeyboardButton("🗑 Удалить отзыв"), KeyboardButton("❌ Отмена")]
    ]

    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
    )


@log_handler
def handle_user_review_rating(chat_id, text):
    """Обработка выбора рейтинга пользователем"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    if text == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        # Возвращаемся к списку бронирований
        from .handlers import show_user_bookings_with_cancel
        show_user_bookings_with_cancel(chat_id, "completed")
        return

    # Обработка удаления отзыва
    if text == "🗑 Удалить отзыв":
        existing_review_id = state_data.get('existing_review_id')
        if existing_review_id:
            try:
                review = Review.objects.get(id=existing_review_id)
                property_name = review.property.name
                review.delete()

                send_telegram_message(
                    chat_id,
                    f"✅ Отзыв о квартире «{property_name}» удален"
                )
            except Review.DoesNotExist:
                send_telegram_message(chat_id, "❌ Отзыв не найден")

        profile.telegram_state = {}
        profile.save()
        from .handlers import show_user_bookings_with_cancel
        show_user_bookings_with_cancel(chat_id, "completed")
        return

    # Обработка рейтинга
    rating = text.count("⭐")
    if rating < 1 or rating > 5:
        send_telegram_message(
            chat_id,
            "Пожалуйста, выберите оценку от 1 до 5 звезд"
        )
        return

    # Сохраняем рейтинг и переходим к тексту
    state_data["review_rating"] = rating
    state_data["state"] = "user_review_text"
    profile.telegram_state = state_data
    profile.save()

    booking_id = state_data.get("review_booking_id")
    booking = Booking.objects.get(id=booking_id)

    text_msg = (
        f"Оценка: {'⭐' * rating}\n\n"
        f"Напишите отзыв о квартире «{booking.property.name}»\n"
        f"или нажмите 'Пропустить текст':"
    )

    keyboard = [
        [KeyboardButton("Пропустить текст")],
        [KeyboardButton("❌ Отмена")]
    ]

    send_telegram_message(
        chat_id,
        text_msg,
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            input_field_placeholder="Напишите ваш отзыв..."
        ).to_dict()
    )


@log_handler
def handle_user_review_text(chat_id, text):
    """Обработка текста отзыва пользователя"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    if text == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        from .handlers import show_user_bookings_with_cancel
        show_user_bookings_with_cancel(chat_id, "completed")
        return

    if text == "Пропустить текст":
        text = ""

    # Сохраняем текст и переходим к фото
    state_data["review_text"] = text
    state_data["state"] = "user_review_photos"
    profile.telegram_state = state_data
    profile.save()

    text_msg = (
        "📷 Хотите добавить фотографии к отзыву?\n"
        "Можете отправить до 3 фотографий или пропустить этот шаг."
    )

    keyboard = [
        [KeyboardButton("📷 Добавить фото")],
        [KeyboardButton("✅ Сохранить без фото")],
        [KeyboardButton("❌ Отмена")]
    ]

    send_telegram_message(
        chat_id,
        text_msg,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
    )


@log_handler
def handle_user_review_photos(chat_id, text):
    """Обработка выбора добавления фото к отзыву"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    if text == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        from .handlers import show_user_bookings_with_cancel
        show_user_bookings_with_cancel(chat_id, "completed")
        return

    if text == "✅ Сохранить без фото":
        save_user_review(chat_id)
        return

    if text == "📷 Добавить фото":
        state_data["state"] = "user_review_uploading"
        state_data["review_photos"] = []
        profile.telegram_state = state_data
        profile.save()

        keyboard = [
            [KeyboardButton("✅ Завершить загрузку")],
            [KeyboardButton("❌ Отмена")]
        ]

        send_telegram_message(
            chat_id,
            "📷 Отправьте фотографии (до 3 штук).\n"
            "После загрузки всех фото нажмите '✅ Завершить загрузку'",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
        )


@log_handler
def handle_user_review_photo_upload(chat_id, update, context):
    """Обработка загрузки фото к отзыву пользователя"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    if state_data.get("state") != "user_review_uploading":
        return False

    photos = state_data.get("review_photos", [])
    if len(photos) >= 3:
        send_telegram_message(
            chat_id,
            "Максимум 3 фотографии. Нажмите '✅ Завершить загрузку'"
        )
        return True

    if update.message and update.message.photo:
        # Берем фото лучшего качества
        photo = max(update.message.photo, key=lambda p: getattr(p, 'file_size', 0) or 0)
        photos.append(photo.file_id)
        state_data["review_photos"] = photos
        profile.telegram_state = state_data
        profile.save()

        send_telegram_message(
            chat_id,
            f"📷 Фото {len(photos)}/3 загружено.\n"
            f"{'Можете добавить еще или ' if len(photos) < 3 else ''}"
            f"нажмите '✅ Завершить загрузку'"
        )
        return True

    return False


@log_handler
def handle_user_review_uploading(chat_id, text):
    """Обработка завершения загрузки фото"""
    profile = _get_profile(chat_id)

    if text == "✅ Завершить загрузку":
        save_user_review(chat_id)
    elif text == "❌ Отмена":
        profile.telegram_state = {}
        profile.save()
        from .handlers import show_user_bookings_with_cancel
        show_user_bookings_with_cancel(chat_id, "completed")


@log_handler
def save_user_review(chat_id):
    """Сохранение отзыва пользователя"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    booking_id = state_data.get("review_booking_id")
    property_id = state_data.get("review_property_id")
    rating = state_data.get("review_rating", 5)
    text = state_data.get("review_text", "")
    photo_ids = state_data.get("review_photos", [])
    review_mode = state_data.get("review_mode", "create")
    existing_review_id = state_data.get("existing_review_id")

    try:
        booking = Booking.objects.get(id=booking_id)
        property_obj = Property.objects.get(id=property_id)

        if review_mode == "edit" and existing_review_id:
            # Обновляем существующий отзыв
            review = Review.objects.get(id=existing_review_id)
            review.rating = rating
            review.text = text
            review.updated_at = timezone.now()
            review.save()

            # Удаляем старые фото отзыва
            ReviewPhoto.objects.filter(review=review).delete()

            action_text = "обновлен"
        else:
            # Создаем новый отзыв
            review = Review.objects.create(
                property=property_obj,
                user=profile.user,
                rating=rating,
                text=text,
                booking_id=booking_id  # Связываем с конкретным бронированием
            )
            action_text = "сохранен"

        # Добавляем фото если есть
        for file_id in photo_ids:
            try:
                # Получаем URL фото из Telegram
                bot_token = settings.TELEGRAM_BOT_TOKEN
                import requests

                file_response = requests.get(
                    f"https://api.telegram.org/bot{bot_token}/getFile",
                    params={"file_id": file_id},
                    timeout=10
                )

                if file_response.status_code == 200:
                    file_path = file_response.json()["result"]["file_path"]
                    file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"

                    ReviewPhoto.objects.create(
                        review=review,
                        image_url=file_url
                    )
            except Exception as e:
                logger.error(f"Error saving review photo: {e}")

        # Отправляем подтверждение
        text_msg = (
            f"✅ Отзыв {action_text}!\n\n"
            f"🏠 Квартира: {property_obj.name}\n"
            f"⭐ Оценка: {'⭐' * rating} ({rating}/5)\n"
        )

        if text:
            text_msg += f"💬 Текст: {text[:100]}{'...' if len(text) > 100 else ''}\n"

        if photo_ids:
            text_msg += f"📷 Фотографий: {len(photo_ids)}\n"

        text_msg += "\nСпасибо за ваш отзыв!"

        keyboard = [
            [KeyboardButton("📋 Мои бронирования")],
            [KeyboardButton("🧭 Главное меню")]
        ]

        send_telegram_message(
            chat_id,
            text_msg,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
        )

        # Уведомляем владельца о новом отзыве
        try:
            owner = property_obj.owner
            if hasattr(owner, 'profile') and owner.profile.telegram_chat_id:
                owner_text = (
                    f"⭐ {'Обновлен отзыв' if review_mode == 'edit' else 'Новый отзыв'} о вашей квартире!\n\n"
                    f"🏠 {property_obj.name}\n"
                    f"⭐ Оценка: {'⭐' * rating} ({rating}/5)\n"
                    f"👤 От: {profile.user.first_name or 'Гость'}\n"
                )

                if text:
                    owner_text += f"💬 {text[:200]}{'...' if len(text) > 200 else ''}\n"

                send_telegram_message(owner.profile.telegram_chat_id, owner_text)
        except Exception as e:
            logger.error(f"Error notifying owner about review: {e}")

    except Exception as e:
        logger.error(f"Error saving user review: {e}", exc_info=True)
        send_telegram_message(
            chat_id,
            "❌ Ошибка при сохранении отзыва. Попробуйте позже."
        )

    # Очищаем состояние
    profile.telegram_state = {}
    profile.save()

    # Возвращаемся к списку бронирований
    from .handlers import show_user_bookings_with_cancel
    show_user_bookings_with_cancel(chat_id, "completed")
