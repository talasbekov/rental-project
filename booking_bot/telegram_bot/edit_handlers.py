from telegram import ReplyKeyboardMarkup, KeyboardButton
from .utils import send_telegram_message
from .constants import (
    STATE_EDIT_PROPERTY_MENU,
    STATE_WAITING_NEW_PRICE,
    STATE_WAITING_NEW_DESCRIPTION,
    STATE_WAITING_NEW_STATUS,
    STATE_PHOTO_MANAGEMENT, _get_profile,
)
from booking_bot.listings.models import Property


# --- Стартовые функции (запрашивают данные) ---

def handle_edit_price_start(chat_id):
    profile = _get_profile(chat_id)
    send_telegram_message(chat_id, "Введите новую цену для квартиры:")

    profile.telegram_state["state"] = STATE_WAITING_NEW_PRICE
    profile.save()


def handle_edit_description_start(chat_id):
    profile = _get_profile(chat_id)
    send_telegram_message(chat_id, "Введите новое описание:")

    profile.telegram_state["state"] = STATE_WAITING_NEW_DESCRIPTION
    profile.save()


def handle_edit_status_start(chat_id):
    profile = _get_profile(chat_id)
    send_telegram_message(chat_id, "Введите новый статус (например: свободна/занята):")

    profile.telegram_state["state"] = STATE_WAITING_NEW_STATUS
    profile.save()


def handle_manage_photos_start(chat_id):
    profile = _get_profile(chat_id)

    keyboard = [
        [KeyboardButton("➕ Добавить фото")],
        [KeyboardButton("🗑 Удалить фото")],
        [KeyboardButton("⬅ Назад")]
    ]

    send_telegram_message(
        chat_id,
        "Управление фото для квартиры. Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True).to_dict()
    )

    profile.telegram_state["state"] = STATE_PHOTO_MANAGEMENT
    profile.save()


# --- Сохранение изменений в БД ---

def save_new_price(chat_id, text):
    profile = _get_profile(chat_id)
    property_id = profile.telegram_state.get("editing_property_id")

    try:
        price = int(text)
        prop = Property.objects.get(id=property_id)
        prop.price_per_day = price
        prop.save()

        send_telegram_message(chat_id, f"✅ Цена обновлена: {price} ₸/сутки")

    except (ValueError, Property.DoesNotExist):
        send_telegram_message(chat_id, "Ошибка! Введите корректную цену числом.")

    profile.telegram_state["state"] = STATE_EDIT_PROPERTY_MENU
    profile.save()


def save_new_description(chat_id, text):
    profile = _get_profile(chat_id)
    property_id = profile.telegram_state.get("editing_property_id")

    try:
        prop = Property.objects.get(id=property_id)
        prop.description = text
        prop.save()
        send_telegram_message(chat_id, "✅ Описание обновлено")

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Ошибка! Квартира не найдена.")

    profile.telegram_state["state"] = STATE_EDIT_PROPERTY_MENU
    profile.save()


def save_new_status(chat_id, text):
    profile = _get_profile(chat_id)
    property_id = profile.telegram_state.get("editing_property_id")

    try:
        prop = Property.objects.get(id=property_id)
        prop.status = text
        prop.save()
        send_telegram_message(chat_id, f"✅ Статус обновлён: {text}")

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Ошибка! Квартира не найдена.")

    profile.telegram_state["state"] = STATE_EDIT_PROPERTY_MENU
    profile.save()


def save_new_photo(chat_id, text):
    # Тут потом добавишь обработку загрузки фото
    send_telegram_message(chat_id, "📷 Фотофункционал пока в разработке.")

    profile = _get_profile(chat_id)
    profile.telegram_state["state"] = STATE_EDIT_PROPERTY_MENU
    profile.save()
