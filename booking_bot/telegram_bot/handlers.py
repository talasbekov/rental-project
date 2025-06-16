import logging
import requests
from datetime import datetime
from .. import settings

from booking_bot.users.models import UserProfile
from .utils import send_telegram_message, _edit_message

logger = logging.getLogger(__name__)

# Actions
ACTION_SEARCH = 'search'
ACTION_SEARCH_ROOMS = 'search_rooms'
ACTION_SEARCH_CLASS = 'search_class'
ACTION_BOOK_START = 'awaiting_start_date'
ACTION_BOOK_END = 'awaiting_end_date'

AVAILABLE_REGIONS = ['Almaty', 'Astana', 'Shymkent']
AVAILABLE_ROOMS = ['1', '2', '3', '4+']
AVAILABLE_CLASSES = [('economy', 'Economy'), ('comfort', 'Comfort'), ('premium', 'Premium')]


def _get_profile(chat_id):
    profile, _ = UserProfile.objects.get_or_create(telegram_chat_id=str(chat_id))
    return profile


def start_command_handler(chat_id):
    profile = _get_profile(chat_id)
    profile.telegram_state = {}
    profile.save()
    text = "👋 Добро пожаловать! Введите /menu для просмотра опций."
    send_telegram_message(chat_id, text)


def menu_command_handler(chat_id):
    text = (
        "🏠 Главное меню:\n"
        "1. Найти квартиру\n"
        "2. Мои бронирования\n"
        "3. Помощь\n\n"
        "Введите номер пункта."
    )
    send_telegram_message(chat_id, text)


def help_command_handler(chat_id):
    text = (
        "🤖 *Помощь*\n"
        "/start — перезапустить бота\n"
        "/menu — показать меню\n"
        "1 — поиск квартир\n"
        "2 — список бронирований\n"
        "3 — это сообщение помощи"
    )
    send_telegram_message(chat_id, text)


def text_message_handler(chat_id, text):
    if text == '1':
        _send_region_buttons(chat_id)
    elif text == '2':
        list_bookings_handler(chat_id)
    elif text == '3':
        help_command_handler(chat_id)
    else:
        send_telegram_message(chat_id, "Не понял. Введите /menu.")


def _send_region_buttons(chat_id):
    keyboard = [[{"text": r, "callback_data": f"search_region|{r}"}] for r in AVAILABLE_REGIONS]
    send_telegram_message(chat_id, "Выберите регион:", {"inline_keyboard": keyboard})


def callback_query_handler(chat_id, data, message_id):
    """Главная точка входа для всех callback_data."""
    parts = data.split('|')
    action = parts[0]
    payload = parts[1] if len(parts) > 1 else None

    if action == 'search_region':
        _handle_search_region(chat_id, payload, message_id)
    elif action == 'search_rooms':
        _handle_search_rooms(chat_id, payload, message_id)
    elif action == 'search_class':
        _handle_search_class(chat_id, payload, message_id)
    elif action == 'book_property':
        _handle_book_property(chat_id, payload)
    elif action == 'cancel_booking':
        _handle_cancel_booking(chat_id, payload)
    else:
        send_telegram_message(chat_id, "Неизвестная команда.")


def _handle_search_region(chat_id, region, message_id):
    profile = _get_profile(chat_id)
    profile.telegram_state = {'action': ACTION_SEARCH, 'region': region}
    profile.save()

    keyboard = [[{"text": r, "callback_data": f"search_rooms|{r}"}] for r in AVAILABLE_ROOMS]
    _edit_message(chat_id, message_id, f"Регион: <b>{region}</b>\nВыберите кол-во комнат:", {"inline_keyboard": keyboard})


def _handle_search_rooms(chat_id, rooms, message_id):
    profile = _get_profile(chat_id)
    state = profile.telegram_state or {}
    state.update({'action': ACTION_SEARCH_ROOMS, 'rooms': rooms})
    profile.telegram_state = state
    profile.save()

    keyboard = [[{"text": label, "callback_data": f"search_class|{key}"}] for key, label in AVAILABLE_CLASSES]
    _edit_message(chat_id, message_id, f"Комнат: <b>{rooms}</b>\nВыберите класс:", {"inline_keyboard": keyboard})


def _handle_search_class(chat_id, cls, message_id):
    profile = _get_profile(chat_id)
    state = profile.telegram_state or {}
    state.update({'action': ACTION_SEARCH_CLASS, 'class': cls})
    profile.telegram_state = state
    profile.save()

    params = {
        'region': state['region'],
        'rooms': state['rooms'],
        'class': cls,
    }
    try:
        url = f"{settings.API_BASE}/properties/"
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        apartments = resp.json()
    except Exception as e:
        logger.error("Error fetching apartments", exc_info=True)
        send_telegram_message(chat_id, "Ошибка при получении списка. Попробуйте позже.")
        return

    if not apartments:
        send_telegram_message(chat_id, "Квартир не найдено.")
    else:
        for apt in apartments[:5]:
            text = (
                f"<b>{apt['title']}</b>\n"
                f"💰 {apt['price']} per night"
            )
            btn = [[{"text": "Забронировать", "callback_data": f"book_property|{apt['id']}"}]]
            send_telegram_message(chat_id, text, {"inline_keyboard": btn})

    # Сброс состояния
    profile.telegram_state = {}
    profile.save()


def _handle_book_property(chat_id, prop_id):
    profile = _get_profile(chat_id)
    profile.telegram_state = {'action': ACTION_BOOK_START, 'property_id': prop_id}
    profile.save()
    send_telegram_message(chat_id, "Введите дату заезда (YYYY-MM-DD):")


def date_input_handler(chat_id, text):
    profile = _get_profile(chat_id)
    state = profile.telegram_state or {}
    action = state.get('action')

    try:
        date_obj = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        send_telegram_message(chat_id, "Неверный формат. Используйте YYYY-MM-DD.")
        return

    if action == ACTION_BOOK_START:
        state.update({'start_date': text, 'action': ACTION_BOOK_END})
        profile.telegram_state = state
        profile.save()
        send_telegram_message(chat_id, "Введите дату выезда (YYYY-MM-DD):")
    elif action == ACTION_BOOK_END:
        start = datetime.strptime(state['start_date'], "%Y-%m-%d").date()
        if date_obj <= start:
            send_telegram_message(chat_id, "Дата выезда должна быть позже заезда.")
            return

        data = {
            'property_id': state['property_id'],
            'start_date': state['start_date'],
            'end_date': text,
        }
        headers = {}
        if getattr(profile, 'jwt', None):
            headers['Authorization'] = f"Bearer {profile.jwt}"

        try:
            resp = requests.post(f"{settings.API_BASE}/api/bookings/", json=data, headers=headers, timeout=5)
            resp.raise_for_status()
            booking = resp.json()
        except Exception:
            logger.exception("Booking error")
            send_telegram_message(chat_id, "Ошибка при бронировании.")
            profile.telegram_state = {}
            profile.save()
            return

        send_telegram_message(chat_id, "✅ Бронирование создано!")
        if booking.get('payment_url'):
            send_telegram_message(chat_id, booking['payment_url'])

        profile.telegram_state = {}
        profile.save()
    else:
        send_telegram_message(chat_id, "Нужно начать бронирование через меню (/menu).")


def list_bookings_handler(chat_id):
    profile = _get_profile(chat_id)
    headers = {}
    if getattr(profile, 'jwt', None):
        headers['Authorization'] = f"Bearer {profile.jwt}"

    try:
        resp = requests.get(f"{settings.API_BASE}/api/bookings/", headers=headers, timeout=5)
        resp.raise_for_status()
        bookings = resp.json()
    except Exception:
        logger.exception("Fetch bookings error")
        send_telegram_message(chat_id, "Ошибка при получении бронирований.")
        return

    if not bookings:
        send_telegram_message(chat_id, "У вас нет активных бронирований.")
    else:
        for b in bookings:
            text = (
                f"🆔 #{b['id']}\n"
                f"{b['property_title']}\n"
                f"{b['start_date']} – {b['end_date']}\n"
                f"Статус: {b['status']}"
            )
            btn = [[{"text": "Отменить", "callback_data": f"cancel_booking|{b['id']}"}]]
            send_telegram_message(chat_id, text, {"inline_keyboard": btn})


def _handle_cancel_booking(chat_id, booking_id):
    profile = _get_profile(chat_id)
    headers = {}
    if getattr(profile, 'jwt', None):
        headers['Authorization'] = f"Bearer {profile.jwt}"

    try:
        resp = requests.delete(f"{settings.API_BASE}/api/bookings/{booking_id}/", headers=headers, timeout=5)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error("Cancel error", exc_info=True)
        send_telegram_message(chat_id, "Не удалось отменить бронирование.")
        return
    except Exception:
        logger.exception("Cancel booking exception")
        send_telegram_message(chat_id, "Сервис недоступен.")
        return

    send_telegram_message(chat_id, "✅ Бронирование отменено.")
