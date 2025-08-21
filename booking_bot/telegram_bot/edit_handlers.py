from telegram import ReplyKeyboardMarkup, KeyboardButton

from .admin_handlers import handle_edit_property_start
from .utils import send_telegram_message
from .constants import (
    STATE_EDIT_PROPERTY_MENU,
    STATE_WAITING_NEW_PRICE,
    STATE_WAITING_NEW_DESCRIPTION,
    STATE_WAITING_NEW_STATUS,
    STATE_PHOTO_MANAGEMENT, _get_profile,
)
from booking_bot.listings.models import Property

# --- Сохранение изменений в БД ---

def save_new_price(chat_id, text):
    """Сохранение новой цены"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    property_id = state_data.get("editing_property_id")

    if text == "❌ Отмена":
        handle_edit_property_start(chat_id, property_id)
        return

    try:
        price = float(text.replace(',', '.'))
        if price <= 0:
            raise ValueError("Цена должна быть положительной")

        prop = Property.objects.get(id=property_id)
        old_price = prop.price_per_day
        prop.price_per_day = price
        prop.save()

        send_telegram_message(
            chat_id,
            f"✅ Цена успешно изменена!\n"
            f"Было: {old_price} ₸\n"
            f"Стало: {price} ₸"
        )

        # Возвращаемся в меню редактирования
        handle_edit_property_start(chat_id, property_id)

    except ValueError:
        send_telegram_message(chat_id, "❌ Неверный формат цены. Введите число.")
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена.")
        profile.telegram_state = {}
        profile.save()


def save_new_description(chat_id, text):
    """Сохранение нового описания"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    property_id = state_data.get("editing_property_id")

    if text == "❌ Отмена":
        handle_edit_property_start(chat_id, property_id)
        return

    try:
        prop = Property.objects.get(id=property_id)
        prop.description = text.strip()
        prop.save()

        send_telegram_message(chat_id, "✅ Описание успешно обновлено!")

        # Возвращаемся в меню редактирования
        handle_edit_property_start(chat_id, property_id)

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена.")
        profile.telegram_state = {}
        profile.save()


def save_new_status(chat_id, text):
    """Сохранение нового статуса"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    property_id = state_data.get("editing_property_id")

    if text == "❌ Отмена":
        handle_edit_property_start(chat_id, property_id)
        return

    if text not in ["Свободна", "На обслуживании"]:
        send_telegram_message(chat_id, "❌ Выберите статус из предложенных вариантов.")
        return

    try:
        prop = Property.objects.get(id=property_id)
        old_status = prop.status
        prop.status = text
        prop.save()

        send_telegram_message(
            chat_id,
            f"✅ Статус успешно изменен!\n"
            f"Было: {old_status}\n"
            f"Стало: {text}"
        )

        # Возвращаемся в меню редактирования
        handle_edit_property_start(chat_id, property_id)

    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена.")
        profile.telegram_state = {}
        profile.save()


def save_new_photo(chat_id, text):
    """Заглушка для управления фото"""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}
    property_id = state_data.get("editing_property_id")

    send_telegram_message(chat_id, "📷 Функционал управления фото пока в разработке.")

    # Возвращаемся в меню редактирования
    handle_edit_property_start(chat_id, property_id)
