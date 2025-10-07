"""Handlers for the booking flow in Telegram bot."""

import logging
import re
from datetime import datetime, date, timedelta

from telegram import KeyboardButton, ReplyKeyboardMarkup

from .constants import (
    log_handler,
    _get_profile,
    STATE_AWAITING_CHECK_IN,
    STATE_AWAITING_CHECK_OUT,
    STATE_AWAITING_CHECK_IN_TIME,
    STATE_AWAITING_CHECK_OUT_TIME,
    STATE_CONFIRM_BOOKING,
    BUTTON_PAY_KASPI,
    BUTTON_PAY_MANUAL,
    BUTTON_CANCEL_BOOKING,
)
from .utils import send_telegram_message
from booking_bot.listings.models import Property
from booking_bot.services.booking_service import calculate_total_price, BookingError

logger = logging.getLogger(__name__)


@log_handler
def handle_booking_start(chat_id: int, property_id: int) -> None:
    profile = _get_profile(chat_id)
    try:
        prop = Property.objects.get(id=property_id, status="Свободна")
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена или уже забронирована.")
        return

    today = date.today()
    tomorrow = today + timedelta(days=1)

    profile.telegram_state.update(
        {"state": STATE_AWAITING_CHECK_IN, "booking_property_id": property_id}
    )
    profile.save()

    text = (
        f"📅 *Бронирование квартиры*\n"
        f"{prop.name}\n\n"
        "Введите дату заезда в формате ДД.MM.ГГГГ или выберите быстрый вариант."
    )
    kb = [
        [KeyboardButton(f"Сегодня ({today.strftime('%d.%m')})")],
        [KeyboardButton(f"Завтра ({tomorrow.strftime('%d.%m')})")],
        [KeyboardButton("❌ Отмена")],
    ]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(
            kb, resize_keyboard=True, input_field_placeholder="Дата заезда"
        ).to_dict(),
    )


@log_handler
def handle_checkin_input(chat_id: int, text: str) -> None:
    try:
        check_in = datetime.strptime(text, "%d.%m.%Y").date()
    except Exception:
        if "Сегодня" in text:
            check_in = date.today()
        else:
            check_in = date.today() + timedelta(days=1)

    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}
    sd.update(
        {"check_in_date": check_in.isoformat(), "state": STATE_AWAITING_CHECK_OUT}
    )
    profile.telegram_state = sd
    profile.save()

    tomorrow = check_in + timedelta(days=1)
    after = tomorrow + timedelta(days=1)
    text = (
        f"Дата заезда: {check_in.strftime('%d.%m.%Y')}\n\n"
        "Введите дату выезда или выберите быстрый вариант."
    )
    kb = [
        [KeyboardButton(f"{tomorrow.strftime('%d.%m')} (+1)")],
        [KeyboardButton(f"{after.strftime('%d.%m')} (+2)")],
        [KeyboardButton("❌ Отмена")],
    ]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(
            kb, resize_keyboard=True, input_field_placeholder="Дата выезда"
        ).to_dict(),
    )


@log_handler
def handle_checkout_input(chat_id: int, text: str) -> None:
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    check_in_str = sd.get("check_in_date")
    if not check_in_str:
        send_telegram_message(chat_id, "Ошибка: дата заезда не найдена.")
        return
    check_in = date.fromisoformat(check_in_str)

    m = re.search(r"\(\s*\+?(\d+)", text)
    if m:
        offset = int(m.group(1))
        check_out = check_in + timedelta(days=offset)
    elif text.startswith("Сегодня"):
        check_out = date.today()
    elif text.startswith("Завтра"):
        check_out = date.today() + timedelta(days=1)
    else:
        try:
            check_out = datetime.strptime(text, "%d.%m.%Y").date()
        except ValueError:
            send_telegram_message(
                chat_id, "Неверный формат даты. Используйте кнопку или ДД.MM.ГГГГ."
            )
            return

    if check_out <= check_in:
        send_telegram_message(chat_id, "Дата выезда должна быть позже даты заезда.")
        return

    sd.update(
        {"check_out_date": check_out.isoformat(), "state": STATE_AWAITING_CHECK_IN_TIME}
    )
    profile.telegram_state = sd
    profile.save()

    text = f"Дата выезда: {check_out.strftime('%d.%m.%Y')}\n\nВыберите время заезда:"
    kb = [
        [KeyboardButton("12:00"), KeyboardButton("14:00")],
        [KeyboardButton("16:00"), KeyboardButton("18:00")],
        [KeyboardButton("❌ Отмена")],
    ]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
    )


@log_handler
def handle_checkin_time(chat_id: int, text: str) -> None:
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    valid_choices = {"12:00", "14:00", "16:00", "18:00"}
    if text not in valid_choices:
        send_telegram_message(
            chat_id, "Пожалуйста, выберите время из предложенных вариантов"
        )
        return

    sd["check_in_time"] = text
    sd["state"] = STATE_AWAITING_CHECK_OUT_TIME
    profile.telegram_state = sd
    profile.save()

    kb = [
        [KeyboardButton("10:00"), KeyboardButton("11:00")],
        [KeyboardButton("12:00"), KeyboardButton("14:00")],
        [KeyboardButton("❌ Отмена")],
    ]
    send_telegram_message(
        chat_id,
        "Выберите время выезда:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
    )


@log_handler
def handle_checkout_time(chat_id: int, text: str) -> None:
    profile = _get_profile(chat_id)
    sd = profile.telegram_state or {}

    valid_choices = {"10:00", "11:00", "12:00", "14:00"}
    if text not in valid_choices:
        send_telegram_message(
            chat_id, "Пожалуйста, выберите время из предложенных вариантов"
        )
        return

    property_id = sd.get("booking_property_id")
    check_in = date.fromisoformat(sd.get("check_in_date"))
    check_out = date.fromisoformat(sd.get("check_out_date"))
    check_in_time = sd.get("check_in_time", "14:00")

    try:
        prop = Property.objects.get(id=property_id)
        total_price = calculate_total_price(prop, check_in, check_out)
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "Квартира не найдена или недоступна.")
        return
    except BookingError as exc:
        logger.info("Cannot calculate price for chat %s: %s", chat_id, exc)
        send_telegram_message(chat_id, f"❌ {exc}")
        return

    sd.update(
        {
            "check_out_time": text,
            "state": STATE_CONFIRM_BOOKING,
            "total_price": float(total_price),
        }
    )
    profile.telegram_state = sd
    profile.save()

    days = (check_out - check_in).days
    text_msg = (
        f"*Подтверждение бронирования*\n\n"
        f"🏠 {prop.name}\n"
        f"📅 Заезд: {check_in.strftime('%d.%m.%Y')} в {check_in_time}\n"
        f"📅 Выезд: {check_out.strftime('%d.%m.%Y')} до {text}\n"
        f"🌙 Ночей: {days}\n"
        f"💰 Итого: *{total_price:,.0f} ₸*"
    )
    kb = [
        [KeyboardButton(BUTTON_PAY_KASPI)],
        [KeyboardButton(BUTTON_PAY_MANUAL)],
        [KeyboardButton(BUTTON_CANCEL_BOOKING)],
    ]
    send_telegram_message(
        chat_id,
        text_msg,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict(),
    )


__all__ = [
    "handle_booking_start",
    "handle_checkin_input",
    "handle_checkout_input",
    "handle_checkin_time",
    "handle_checkout_time",
]
