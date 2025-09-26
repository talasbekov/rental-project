"""Логика оформления бронирования и оплаты в Telegram-боте."""

import logging
from datetime import date

from telegram import KeyboardButton, ReplyKeyboardMarkup

from booking_bot import settings
from booking_bot.services.booking_service import (
    BookingError,
    BookingRequest,
    create_booking,
)
from booking_bot.bookings.tasks import cancel_expired_booking
from booking_bot.listings.models import Property
from booking_bot.payments import (
    initiate_payment as kaspi_initiate_payment,
    KaspiPaymentError,
)
from booking_bot.notifications.delivery import (
    build_confirmation_message,
    log_codes_delivery,
)

from .constants import log_handler, _get_profile
from .utils import send_telegram_message

logger = logging.getLogger(__name__)


@log_handler
def handle_payment_confirmation(chat_id: int) -> None:
    """Сбор данных бронирования и запуск платежного процесса."""
    profile = _get_profile(chat_id)
    state_data = profile.telegram_state or {}

    property_id = state_data.get("booking_property_id")
    check_in_str = state_data.get("check_in_date")
    check_out_str = state_data.get("check_out_date")

    if not all([property_id, check_in_str, check_out_str]):
        send_telegram_message(
            chat_id, "❌ Ошибка: недостаточно данных для бронирования."
        )
        return

    try:
        property_obj = Property.objects.get(id=property_id)
        check_in = date.fromisoformat(check_in_str)
        check_out = date.fromisoformat(check_out_str)

        request = BookingRequest(
            user=profile.user,
            property=property_obj,
            start_date=check_in,
            end_date=check_out,
            check_in_time=state_data.get("check_in_time", "14:00"),
            check_out_time=state_data.get("check_out_time", "12:00"),
            status="pending_payment",
            hold_calendar=True,
        )

        try:
            booking = create_booking(request)
        except BookingError as exc:
            logger.info("Booking creation failed for chat %s: %s", chat_id, exc)
            send_telegram_message(chat_id, f"❌ Невозможно создать бронирование: {exc}")
            return

        if booking.expires_at:
            cancel_expired_booking.apply_async(args=[booking.id], eta=booking.expires_at)

        logger.info(
            "Создано бронирование %s для пользователя %s (Telegram)",
            booking.id,
            profile.user.username,
        )

        send_telegram_message(
            chat_id, "⏳ Создаем платеж...\nПожалуйста, подождите..."
        )

        try:
            payment_info = kaspi_initiate_payment(
                booking_id=booking.id,
                amount=float(booking.total_price),
                description=(
                    f"Бронирование {property_obj.name} с "
                    f"{check_in.strftime('%d.%m.%Y')} по {check_out.strftime('%d.%m.%Y')}"
                ),
            )

            if not payment_info or not payment_info.get("checkout_url"):
                raise KaspiPaymentError("Не удалось получить ссылку для оплаты")

            kaspi_payment_id = payment_info.get("payment_id")
            if kaspi_payment_id:
                booking.kaspi_payment_id = kaspi_payment_id
                booking.save(update_fields=["kaspi_payment_id"])

            checkout_url = payment_info["checkout_url"]

            if settings.DEBUG:
                import time

                time.sleep(2)
                booking.status = "confirmed"
                booking.save(update_fields=["status", "updated_at"])
                send_booking_confirmation(chat_id, booking)
                profile.telegram_state = {}
                profile.save()
                logger.info(
                    "Бронирование %s автоматически подтверждено (DEBUG режим)",
                    booking.id,
                )
            else:
                buttons = [
                    [KeyboardButton("📋 Мои бронирования")],
                    [KeyboardButton("🧭 Главное меню")],
                ]
                send_telegram_message(
                    chat_id,
                    (
                        f"✅ Бронирование создано!\n"
                        f"📋 Номер брони: #{booking.id}\n\n"
                        f"💳 Для завершения бронирования оплатите:\n{checkout_url}\n\n"
                        f"⏰ Ссылка действительна 15 минут"
                    ),
                    reply_markup=ReplyKeyboardMarkup(
                        buttons, resize_keyboard=True
                    ).to_dict(),
                )
                profile.telegram_state = {}
                profile.save()
                logger.info(
                    "Отправлена ссылка на оплату для бронирования %s",
                    booking.id,
                )
        except KaspiPaymentError as exc:
            booking.status = "payment_failed"
            booking.save(update_fields=["status", "updated_at"])
            logger.error("Kaspi payment error for booking %s: %s", booking.id, exc)
            send_telegram_message(
                chat_id,
                "❌ Ошибка при создании платежа.\n"
                "Попробуйте позже или обратитесь в поддержку.\n\n"
                f"Код ошибки: {booking.id}",
            )
    except Property.DoesNotExist:
        send_telegram_message(chat_id, "❌ Квартира не найдена.")
    except Exception as exc:  # noqa: BLE001 - логируем неожиданную ошибку
        logger.error("Ошибка при создании бронирования: %s", exc, exc_info=True)
        send_telegram_message(
            chat_id,
            "❌ Произошла ошибка при создании бронирования.\n"
            "Попробуйте позже или обратитесь в поддержку.",
        )


def send_booking_confirmation(chat_id: int, booking) -> None:
    """Отправка информации после успешной оплаты."""
    text = build_confirmation_message(booking)
    codes_block = log_codes_delivery(
        booking, channel="telegram", recipient=str(chat_id)
    )
    if codes_block:
        text += f"\n{codes_block}"

    buttons = [[KeyboardButton("📋 Мои бронирования")], [KeyboardButton("🧭 Главное меню")]]
    send_telegram_message(
        chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True).to_dict(),
        parse_mode="HTML",
    )

    try:
        from .handlers import prompt_review

        prompt_review(chat_id, booking)
    except Exception:  # noqa: BLE001 - мягко игнорируем ошибки импорта/отправки отзыва
        logger.exception(
            "Не удалось отправить запрос отзыва для бронирования %s", booking.id
        )

    logger.info(
        "Отправлено подтверждение бронирования %s пользователю %s",
        booking.id,
        booking.user.username,
    )
