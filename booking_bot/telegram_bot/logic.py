import logging
import requests
from .. import settings
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property
from .utils import send_telegram_message, _edit_message

logger = logging.getLogger(__name__)

# State action constants
ACTION_SEARCH_SELECTING_ROOMS = 'search_selecting_rooms'
ACTION_SEARCH_SELECTING_CLASS = 'search_selecting_class'
ACTION_SEARCH_STARTED = 'search_started'
ACTION_BOOKING_AWAITING_START_DATE = 'awaiting_start_date'

# Available filter options
AVAILABLE_REGIONS = ['Almaty', 'Astana', 'Shymkent']
AVAILABLE_ROOM_COUNTS = ['1', '2', '3', '4+']
AVAILABLE_PROPERTY_CLASSES = [('economy', 'Economy'), ('comfort', 'Comfort'), ('premium', 'Premium')]


def get_user_telegram_state(profile: UserProfile) -> dict:
    state = profile.telegram_state or {}
    return {
        'action': state.get('action'),
        'data': state.get('data', {})
    }


def set_user_telegram_state(profile: UserProfile, action: str, data: dict = None):
    profile.telegram_state = {'action': action, 'data': data or {}}
    profile.save()


def get_region_display_name(region_key: str) -> str:
    return region_key  # or map to human-friendly names


def get_class_display_name(class_key: str) -> str:
    return dict(AVAILABLE_PROPERTY_CLASSES).get(class_key, class_key)


def handle_search_region(chat_id: int, region_key: str, message_id: int):
    profile = UserProfile.objects.filter(telegram_chat_id=str(chat_id)).first()
    if not profile:
        send_telegram_message(chat_id, "Please /start first.")
        return
    set_user_telegram_state(profile, ACTION_SEARCH_SELECTING_ROOMS, data={"region": region_key})
    buttons = [[InlineKeyboardButton(f"{rooms} rooms", callback_data=f"search_rooms_{rooms}")] for rooms in AVAILABLE_ROOM_COUNTS]
    _edit_message(chat_id, message_id,
                  f"Region: <b>{get_region_display_name(region_key)}</b>\nNow select number of rooms:",
                  reply_markup=InlineKeyboardMarkup(buttons))


def handle_search_rooms(chat_id: int, selected_rooms_str: str, message_id: int):
    profile = UserProfile.objects.filter(telegram_chat_id=str(chat_id)).first()
    if not profile:
        send_telegram_message(chat_id, "Please /start first.")
        return
    rooms_val = 4 if selected_rooms_str == "4+" else int(selected_rooms_str)
    state = get_user_telegram_state(profile)["data"]
    state["rooms"] = rooms_val
    set_user_telegram_state(profile, ACTION_SEARCH_SELECTING_CLASS, data=state)
    buttons = [[InlineKeyboardButton(display, callback_data=f"search_class_{key}")] for key, display in AVAILABLE_PROPERTY_CLASSES]
    _edit_message(chat_id, message_id,
                  f"Rooms: <b>{selected_rooms_str}</b>\nSelect property class:",
                  reply_markup=InlineKeyboardMarkup(buttons))


def handle_search_class(chat_id: int, class_key: str, message_id: int):
    profile = UserProfile.objects.filter(telegram_chat_id=str(chat_id)).first()
    if not profile:
        send_telegram_message(chat_id, "Please /start first.")
        return
    state = get_user_telegram_state(profile)["data"]
    state["class"] = class_key
    set_user_telegram_state(profile, ACTION_SEARCH_STARTED, data=state)
    _edit_message(
        chat_id, message_id,
        (
            f"Filters complete:\n"
            f"• Region: <b>{get_region_display_name(state['region'])}</b>\n"
            f"• Rooms: <b>{state['rooms']}</b>\n"
            f"• Class: <b>{get_class_display_name(class_key)}</b>\n\n"
            "Fetching apartments..."
        )
    )
    apartments = Property.objects.filter(
        region=state['region'],
        number_of_rooms=state['rooms'],
        property_class=state['class'],
        status='available'
    )[:5]
    if not apartments:
        send_telegram_message(chat_id, "No apartments found matching your criteria.")
    for apt in apartments:
        text = (
            f"<b>{apt.name}</b>\n"
            f"Price: {apt.price_per_day} KZT/day\n"
            f"Rooms: {apt.number_of_rooms}\n"
            f"Class: {get_class_display_name(apt.property_class)}\n"
            f"Area: {apt.area} m²"
        )
        button = InlineKeyboardButton(
            "Book this apartment", callback_data=f"book_property_{apt.id}"
        )
        send_telegram_message(chat_id, text, reply_markup=InlineKeyboardMarkup([[button]]))
    set_user_telegram_state(profile, None, {})


def handle_book_property(chat_id: int, property_id: str, message_id: int):
    profile = UserProfile.objects.filter(telegram_chat_id=str(chat_id)).first()
    if not profile:
        send_telegram_message(chat_id, "Please /start first.")
        return
    set_user_telegram_state(profile, ACTION_BOOKING_AWAITING_START_DATE,
                             data={"property_id": property_id})
    send_telegram_message(
        chat_id,
        f"You are booking property <b>{property_id}</b>. Please send the check-in date (YYYY-MM-DD)."
    )

async def cancel_booking_callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat.id)
    profile = UserProfile.objects.filter(telegram_chat_id=chat_id).first()
    token = context.user_data.get('jwt_access_token')
    if not profile or not token:
        await context.bot.send_message(chat_id=chat_id,
                                       text="Error: User not authenticated. Please /start again.")
        return
    booking_id = query.data.replace("cancel_booking_", "")
    api_url = f"{settings.SITE_URL}/api/v1/bookings/{booking_id}/"
    try:
        resp = requests.delete(api_url,
                               headers={'Authorization': f'Bearer {token}'},
                               timeout=5)
        resp.raise_for_status()
        await query.edit_message_text(text=f"Booking ID {booking_id} has been successfully cancelled.")
        logger.info(f"Booking ID {booking_id} cancelled successfully by user {chat_id}.")
    except requests.exceptions.HTTPError as e:
        error_message = f"Failed to cancel booking ID {booking_id}."
        if e.response is not None:
            if e.response.status_code == 404:
                error_message = f"Booking ID {booking_id} not found or already processed."
            elif e.response.status_code == 403:
                error_message = f"You do not have permission to cancel this booking or it cannot be cancelled now."
            else:
                try:
                    details = e.response.json()
                    errors = []
                    if isinstance(details, dict):
                        for k, v in details.items():
                            if isinstance(v, list):
                                errors.append(f"{k}: {', '.join(v)}")
                            else:
                                errors.append(f"{k}: {v}")
                    elif isinstance(details, list):
                        errors.extend(details)
                    else:
                        errors.append(str(details))
                    error_message += " Details: " + "; ".join(errors)
                except ValueError:
                    error_message += f" Response: {e.response.text}"
        logger.error(error_message, exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=error_message)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error cancelling booking {booking_id} for {chat_id}: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id,
                                       text="Error connecting to service. Please try again later.")
