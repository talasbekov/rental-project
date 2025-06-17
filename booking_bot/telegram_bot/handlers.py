import logging
import requests
from datetime import datetime
from .. import settings

from booking_bot.users.models import UserProfile
from booking_bot.listings.models import City, District, Property # Added City, District, Property
from .utils import send_telegram_message, _edit_message

logger = logging.getLogger(__name__)

# Actions
ACTION_SEARCH = 'search'
ACTION_SEARCH_ROOMS = 'search_rooms'
ACTION_SEARCH_CLASS = 'search_class'
ACTION_BOOK_START = 'awaiting_start_date'
ACTION_BOOK_END = 'awaiting_end_date'

# AVAILABLE_REGIONS = ['Almaty', 'Astana', 'Shymkent'] # Deprecated, using City model
AVAILABLE_ROOMS = ['1', '2', '3', '4+'] # Kept for now, could be dynamic later
AVAILABLE_CLASSES = [('economy', 'Economy'), ('comfort', 'Comfort'), ('premium', 'Premium')] # Kept for now


def _get_profile(chat_id):
    profile, _ = UserProfile.objects.get_or_create(telegram_chat_id=str(chat_id))
    return profile


def start_command_handler(chat_id):
    profile = _get_profile(chat_id)
    profile.telegram_state = {}
    profile.save()
    text = "Привет! Я ЖильеGO — помогу быстро найти и забронировать квартиру на сутки."
    keyboard = [
        [{"text": "Поиск квартир", "callback_data": "main_menu|search"}],
        [{"text": "Мои бронирования", "callback_data": "main_menu|my_bookings"}],
        [{"text": "Статус текущей брони", "callback_data": "main_menu|current_status"}],
        [{"text": "Помощь", "callback_data": "main_menu|help"}],
    ]
    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})

# --- menu_command_handler and text_message_handler are deprecated by button menu ---
# def menu_command_handler(chat_id):
#     text = (
#         "🏠 Главное меню:\n"
#         "1. Найти квартиру\n"
#         "2. Мои бронирования\n"
#         "3. Помощь\n\n"
#         "Введите номер пункта."
#     )
#     send_telegram_message(chat_id, text)


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

# def text_message_handler(chat_id, text):
#     if text == '1':
#         _send_region_buttons(chat_id)
#     elif text == '2':
#         list_bookings_handler(chat_id)
#     elif text == '3':
#         help_command_handler(chat_id)
#     else:
#         send_telegram_message(chat_id, "Не понял. Введите /menu.")


def _send_city_buttons(chat_id, message_id=None): # Renamed, message_id for potential edit
    cities = City.objects.all()
    if not cities:
        send_telegram_message(chat_id, "Города для поиска не найдены.")
        return
    keyboard = [[{"text": city.name, "callback_data": f"select_city|{city.id}"}] for city in cities]
    text = "Выберите город:"
    if message_id:
        _edit_message(chat_id, message_id, text, {"inline_keyboard": keyboard})
    else:
        send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})


def callback_query_handler(chat_id, data, message_id):
    """Главная точка входа для всех callback_data."""
    parts = data.split('|')
    action = parts[0]
    payload = parts[1] if len(parts) > 1 else None

    # Added for main menu
    if action == 'main_menu':
        if payload == 'search':
            _send_city_buttons(chat_id, message_id)
            return
        elif payload == 'my_bookings':
            list_bookings_handler(chat_id)
            return
        elif payload == 'current_status':
            # For now, same as my_bookings, can be filtered later
            list_bookings_handler(chat_id)
            return
        elif payload == 'help':
            help_command_handler(chat_id)
            return

    # Logic for search_region, search_rooms, search_class needs to be updated for City/District IDs
    if action == 'select_city': # Changed from search_region
        city_id = int(payload)
        profile = _get_profile(chat_id)
        profile.telegram_state = {'action': 'city_selected','city_id': city_id}
        profile.save()

        districts = District.objects.filter(city_id=city_id)
        if not districts:
            _edit_message(chat_id, message_id, f"В этом городе районы не найдены. Попробуйте другой город или продолжите без указания района.") # Handle no districts
            # Potentially proceed to room selection directly or offer other options
            # For now, just informing.
            return
        keyboard = [[{"text": d.name, "callback_data": f"select_district|{d.id}"}] for d in districts]
        try:
            city_name = City.objects.get(id=city_id).name
            _edit_message(chat_id, message_id, f"Город: <b>{city_name}</b>\nВыберите район:", {"inline_keyboard": keyboard})
        except City.DoesNotExist:
             _edit_message(chat_id, message_id, "Выбранный город не найден. Пожалуйста, начните заново.")
        return # Important to return after handling

    elif action == 'select_district': # Changed from search_rooms
        district_id = int(payload)
        profile = _get_profile(chat_id)
        state = profile.telegram_state or {}
        state.update({'action': 'district_selected','district_id': district_id})
        profile.telegram_state = state
        profile.save()

        # Now ask for rooms
        keyboard = [[{"text": r, "callback_data": f"select_rooms|{r}"}] for r in AVAILABLE_ROOMS] # AVAILABLE_ROOMS still hardcoded
        try:
            district_name = District.objects.get(id=district_id).name
            _edit_message(chat_id, message_id, f"Район: <b>{district_name}</b>\nВыберите кол-во комнат:", {"inline_keyboard": keyboard})
        except District.DoesNotExist:
            _edit_message(chat_id, message_id, "Выбранный район не найден. Пожалуйста, начните заново.")
        return # Important

    elif action == 'select_rooms': # Changed from search_class
        rooms = payload # rooms is a string like '1' or '4+'
        profile = _get_profile(chat_id)
        state = profile.telegram_state or {}
        state.update({'action': 'rooms_selected','rooms': rooms})
        profile.telegram_state = state
        profile.save()

        keyboard = [[{"text": label, "callback_data": f"select_class|{key}"}] for key, label in AVAILABLE_CLASSES] # AVAILABLE_CLASSES still hardcoded
        _edit_message(chat_id, message_id, f"Комнат: <b>{rooms}</b>\nВыберите класс жилья:", {"inline_keyboard": keyboard})
        return # Important

    elif action == 'select_class': # This is the final step of search filters
        property_class_key = payload
        profile = _get_profile(chat_id)
        state = profile.telegram_state or {}
        # state should contain city_id, district_id, rooms
        if not all(k in state for k in ['city_id', 'district_id', 'rooms']):
            send_telegram_message(chat_id, "Ошибка: не все параметры поиска выбраны. Начните поиск заново.")
            profile.telegram_state = {} # Reset state
            profile.save()
            return

        params = {
            'city_id': state['city_id'],
            'district_id': state['district_id'],
            'number_of_rooms': state['rooms'], # Ensure API expects 'number_of_rooms' if 'rooms' was '4+'
            'property_class': property_class_key,
        }
        # Handle '4+' rooms case for API if needed. Assuming API handles it or it means 'gte: 4'.
        if params['number_of_rooms'] == '4+':
            params['number_of_rooms_gte'] = 4 # Example: if API supports range queries
            del params['number_of_rooms']     # Or adjust as per API spec

        try:
            # IMPORTANT: The API endpoint /properties/ and its filtering capabilities
            # might need to be updated to support city_id, district_id, rooms, property_class.
            url = f"{settings.API_BASE}/properties/" # Assuming API_BASE is correct
            logger.info(f"Searching properties with params: {params}")"
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            apartments = resp.json()
        except Exception as e:
            logger.error(f"Error fetching apartments: {e}", exc_info=True)
            _edit_message(chat_id, message_id, "Ошибка при получении списка квартир. Попробуйте позже.")
            return

        if not apartments:
            _edit_message(chat_id, message_id, "По вашим параметрам квартиры не найдены. Попробуйте изменить фильтры.")
        else:
            # Clear the current message (filter selection) before sending results
            _edit_message(chat_id, message_id, "Вот что мы нашли:")
            for apt in apartments[:5]: # Limiting to 5 results for now
                # The apartment serialization from the API needs to provide these fields:
                # title, price, id. And ideally address, description for the card.
                apt_title = apt.get('name', apt.get('title', 'Не указано'))
                apt_price = apt.get('price_per_day', apt.get('price', 'N/A'))
                apt_id = apt.get('id')
                text = f"<b>{apt_title}</b>\nЦена: {apt_price} за ночь"
                if apt_id:
                    keyboard_book = [[{"text": "Забронировать", "callback_data": f"book_property|{apt_id}"}]]
                    send_telegram_message(chat_id, text, {"inline_keyboard": keyboard_book})
                else:
                    send_telegram_message(chat_id, text)

        # Reset state after search completion
        profile.telegram_state = {}
        profile.save()
        return

    elif action == 'book_property':
        _handle_book_property(chat_id, payload)
    elif action == 'cancel_booking':
        _handle_cancel_booking(chat_id, payload)
    else:
        send_telegram_message(chat_id, "Неизвестная команда.")

# Old handlers are removed or incorporated above.

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
