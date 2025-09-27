"""Общие функции доставки уведомлений о бронировании для бот-платформ."""

import html
import logging
from typing import Optional

from django.contrib.auth import get_user_model

from booking_bot.core.models import AuditLog

logger = logging.getLogger(__name__)

User = get_user_model()


def build_confirmation_message(booking, include_owner_contact: bool = True) -> str:
    """Формирует текст уведомления о подтверждении бронирования."""
    property_obj = booking.property
    parts = [
        "<b>✅ Оплата подтверждена!</b>\n\n",
        "🎉 Ваше бронирование успешно оформлено!\n\n",
        "<b>Детали бронирования:</b>\n",
        f"Номер брони: #{booking.id}\n",
        f"Квартира: {html.escape(property_obj.name)}\n",
        f"Адрес: {html.escape(property_obj.address or '')}\n",
        f"Заезд: {booking.start_date.strftime('%d.%m.%Y')}\n",
        f"Выезд: {booking.end_date.strftime('%d.%m.%Y')}\n",
        f"Стоимость: {booking.total_price:,.0f} ₸\n",
    ]

    if property_obj.entry_instructions:
        parts.append(
            "\n📝 <b>Инструкции по заселению:</b>\n"
            f"{html.escape(property_obj.entry_instructions)}\n"
        )

    if include_owner_contact:
        owner_phone = getattr(getattr(property_obj.owner, "profile", None), "phone_number", "")
        if owner_phone:
            parts.append(f"\n📞 <b>Контакт владельца:</b> {html.escape(owner_phone)}\n")

    parts.append("\n💬 Желаем приятного отдыха!")
    return "".join(parts)

def log_codes_delivery(booking, channel: str, recipient: Optional[str]) -> str:
    """Возвращает строку с кодами доступа и пишет данные в AuditLog."""
    property_obj = booking.property
    user: User = booking.user
    codes = property_obj.get_access_codes(user)

    AuditLog.log(
        user=user,
        action="send_code",
        obj=property_obj,
        details={
            "booking_id": booking.id,
            "channel": channel,
            "codes_sent": list(codes.keys()),
        },
        telegram_chat_id=recipient if channel == "telegram" else "",
        whatsapp_phone=recipient if channel == "whatsapp" else "",
    )

    parts = []
    if codes.get("digital_lock_code"):
        parts.append(
            f"🔐 <b>Код от замка:</b> <code>{html.escape(codes['digital_lock_code'])}</code>"
        )
    if codes.get("key_safe_code"):
        parts.append(
            f"🔑 <b>Код от сейфа:</b> <code>{html.escape(codes['key_safe_code'])}</code>"
        )
    if codes.get("entry_code"):
        parts.append(
            f"🚪 <b>Код домофона:</b> <code>{html.escape(codes['entry_code'])}</code>"
        )
    if codes.get("owner_phone") and not getattr(
        getattr(property_obj.owner, "profile", None), "phone_number", None
    ):
        parts.append(
            f"📞 <b>Контакт владельца:</b> {html.escape(codes['owner_phone'])}"
        )

    return "\n".join(parts)
