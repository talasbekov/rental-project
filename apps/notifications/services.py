"""Notification services for sending emails and Telegram messages."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings  # type: ignore
from django.core.mail import send_mail  # type: ignore
from django.template.loader import render_to_string  # type: ignore
from django.utils.html import strip_tags  # type: ignore

if TYPE_CHECKING:  # pragma: no cover
    from apps.users.models import CustomUser
    from apps.bookings.models import Booking

logger = logging.getLogger(__name__)


# ============================================================================
# EMAIL NOTIFICATIONS
# ============================================================================

def send_email_notification(
    recipient_email: str,
    subject: str,
    template_name: str,
    context: dict,
    *,
    html_message: str | None = None,
) -> bool:
    """
    Универсальная функция отправки email уведомлений.

    Args:
        recipient_email: Email получателя
        subject: Тема письма
        template_name: Путь к Django template (опционально)
        context: Контекст для рендеринга template
        html_message: HTML-версия письма (опционально)

    Returns:
        bool: True если письмо отправлено успешно
    """
    try:
        # Рендерим текстовую версию из HTML
        if html_message:
            text_message = strip_tags(html_message)
        elif template_name:
            html_message = render_to_string(template_name, context)
            text_message = strip_tags(html_message)
        else:
            text_message = context.get("message", "")
            html_message = None

        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Email sent successfully to {recipient_email}: {subject}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {e}", exc_info=True)
        return False


def send_booking_confirmation_email(booking: "Booking") -> bool:
    """Отправка подтверждения бронирования гостю."""
    subject = f"Бронирование #{booking.booking_code} подтверждено!"

    context = {
        "booking": booking,
        "guest_name": booking.guest.username or booking.guest.email,
        "property_title": booking.property.title,
        "check_in": booking.check_in.strftime("%d.%m.%Y"),
        "check_out": booking.check_out.strftime("%d.%m.%Y"),
        "total_nights": booking.total_nights,
        "total_price": booking.total_price,
        "booking_code": booking.booking_code,
    }

    html_message = f"""
    <html>
    <body>
        <h2>Здравствуйте, {context['guest_name']}!</h2>
        <p>Ваше бронирование успешно подтверждено.</p>

        <h3>Детали бронирования:</h3>
        <ul>
            <li><strong>Код брони:</strong> {context['booking_code']}</li>
            <li><strong>Объект:</strong> {context['property_title']}</li>
            <li><strong>Заезд:</strong> {context['check_in']}</li>
            <li><strong>Выезд:</strong> {context['check_out']}</li>
            <li><strong>Ночей:</strong> {context['total_nights']}</li>
            <li><strong>Итого:</strong> {context['total_price']} ₸</li>
        </ul>

        <p>За 24 часа до заезда вы получите инструкции по заселению.</p>

        <p>С уважением,<br>Команда ЖильеGO</p>
    </body>
    </html>
    """

    return send_email_notification(
        recipient_email=booking.guest.email,
        subject=subject,
        template_name=None,
        context=context,
        html_message=html_message,
    )


def send_booking_reminder_email(booking: "Booking") -> bool:
    """Напоминание о предстоящем заезде (за 24 часа)."""
    subject = f"Напоминание: Заезд завтра в {booking.property.title}"

    context = {
        "booking": booking,
        "guest_name": booking.guest.username or booking.guest.email,
        "property_title": booking.property.title,
        "check_in": booking.check_in.strftime("%d.%m.%Y"),
        "check_in_time": booking.property.check_in_from.strftime("%H:%M"),
        "property_address": booking.property.address_line,
        "realtor_phone": booking.property.owner.phone,
    }

    html_message = f"""
    <html>
    <body>
        <h2>Здравствуйте, {context['guest_name']}!</h2>
        <p>Напоминаем, что завтра ваш заезд в <strong>{context['property_title']}</strong>.</p>

        <h3>Информация о заселении:</h3>
        <ul>
            <li><strong>Дата заезда:</strong> {context['check_in']}</li>
            <li><strong>Время заезда:</strong> с {context['check_in_time']}</li>
            <li><strong>Адрес:</strong> {context['property_address']}</li>
        </ul>

        <p><strong>Контакт владельца:</strong> {context['realtor_phone']}</p>

        <p>Инструкции по заселению будут отправлены вам в день заезда.</p>

        <p>Хорошего отдыха!<br>Команда ЖильеGO</p>
    </body>
    </html>
    """

    return send_email_notification(
        recipient_email=booking.guest.email,
        subject=subject,
        template_name=None,
        context=context,
        html_message=html_message,
    )


def send_booking_expired_email(booking: "Booking") -> bool:
    """Уведомление об истечении времени оплаты."""
    subject = f"Бронирование #{booking.booking_code} отменено"

    context = {
        "booking": booking,
        "guest_name": booking.guest.username or booking.guest.email,
        "property_title": booking.property.title,
    }

    html_message = f"""
    <html>
    <body>
        <h2>Здравствуйте, {context['guest_name']}!</h2>
        <p>К сожалению, время на оплату бронирования истекло.</p>

        <p><strong>Бронирование #{context['booking_code']}</strong> для
        <strong>{context['property_title']}</strong> отменено.</p>

        <p>Вы можете создать новое бронирование в любое время.</p>

        <p>С уважением,<br>Команда ЖильеGO</p>
    </body>
    </html>
    """

    return send_email_notification(
        recipient_email=booking.guest.email,
        subject=subject,
        template_name=None,
        context=context,
        html_message=html_message,
    )


def send_new_booking_to_realtor_email(booking: "Booking") -> bool:
    """Уведомление риелтору о новом бронировании."""
    subject = f"Новое бронирование #{booking.booking_code}"

    context = {
        "booking": booking,
        "realtor_name": booking.property.owner.username or booking.property.owner.email,
        "guest_name": booking.guest.username or booking.guest.email,
        "guest_phone": booking.guest.phone,
        "property_title": booking.property.title,
        "check_in": booking.check_in.strftime("%d.%m.%Y"),
        "check_out": booking.check_out.strftime("%d.%m.%Y"),
        "total_price": booking.total_price,
    }

    html_message = f"""
    <html>
    <body>
        <h2>Здравствуйте, {context['realtor_name']}!</h2>
        <p>У вас новое бронирование!</p>

        <h3>Детали бронирования:</h3>
        <ul>
            <li><strong>Код:</strong> {context['booking'].booking_code}</li>
            <li><strong>Объект:</strong> {context['property_title']}</li>
            <li><strong>Гость:</strong> {context['guest_name']}</li>
            <li><strong>Телефон гостя:</strong> {context['guest_phone']}</li>
            <li><strong>Даты:</strong> {context['check_in']} - {context['check_out']}</li>
            <li><strong>Доход:</strong> {context['total_price']} ₸</li>
        </ul>

        <p>Проверьте объект к дате заезда!</p>

        <p>С уважением,<br>Команда ЖильеGO</p>
    </body>
    </html>
    """

    return send_email_notification(
        recipient_email=booking.property.owner.email,
        subject=subject,
        template_name=None,
        context=context,
        html_message=html_message,
    )


# ============================================================================
# TELEGRAM NOTIFICATIONS
# ============================================================================

def send_telegram_notification(telegram_id: int, message: str) -> bool:
    """
    Отправка Telegram уведомления.

    Args:
        telegram_id: Telegram ID пользователя
        message: Текст сообщения

    Returns:
        bool: True если сообщение отправлено успешно
    """
    try:
        # TODO: Интеграция с Telegram Bot API
        # from telegram import Bot
        # bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        # bot.send_message(chat_id=telegram_id, text=message, parse_mode='HTML')

        logger.info(f"[TELEGRAM] Would send to {telegram_id}: {message[:50]}...")
        return True

    except Exception as e:
        logger.error(f"Failed to send Telegram message to {telegram_id}: {e}", exc_info=True)
        return False


def send_telegram_booking_notification(user: "CustomUser", booking: "Booking") -> bool:
    """Отправка уведомления о бронировании в Telegram."""
    if not user.telegram_id:
        logger.warning(f"User {user.email} has no Telegram ID")
        return False

    message = f"""
🏠 <b>Новое бронирование #{booking.booking_code}</b>

📍 Объект: {booking.property.title}
📅 Даты: {booking.check_in.strftime("%d.%m.%Y")} - {booking.check_out.strftime("%d.%m.%Y")}
🌙 Ночей: {booking.total_nights}
💰 Сумма: {booking.total_price} ₸

Подробности в личном кабинете.
    """.strip()

    return send_telegram_notification(user.telegram_id, message)


# ============================================================================
# IN-APP NOTIFICATIONS
# ============================================================================

def create_in_app_notification(user: "CustomUser", title: str, message: str) -> bool:
    """
    Создание in-app уведомления в базе данных.

    Args:
        user: Пользователь-получатель
        title: Заголовок уведомления
        message: Текст уведомления

    Returns:
        bool: True если уведомление создано успешно
    """
    try:
        from .models import Notification

        Notification.objects.create(
            user=user,
            title=title,
            message=message,
        )

        logger.info(f"In-app notification created for {user.email}: {title}")
        return True

    except Exception as e:
        logger.error(f"Failed to create in-app notification for {user.email}: {e}", exc_info=True)
        return False


def notify_user_all_channels(
    user: "CustomUser",
    title: str,
    message: str,
    email_html: str | None = None,
) -> dict[str, bool]:
    """
    Отправка уведомления пользователю по всем доступным каналам.

    Args:
        user: Пользователь-получатель
        title: Заголовок уведомления
        message: Текст уведомления
        email_html: HTML версия для email (опционально)

    Returns:
        dict: Результаты отправки по каждому каналу
    """
    results = {
        "email": False,
        "telegram": False,
        "in_app": False,
    }

    # Email
    if user.email:
        results["email"] = send_email_notification(
            recipient_email=user.email,
            subject=title,
            template_name=None,
            context={"message": message},
            html_message=email_html,
        )

    # Telegram
    if user.telegram_id:
        results["telegram"] = send_telegram_notification(user.telegram_id, message)

    # In-app
    results["in_app"] = create_in_app_notification(user, title, message)

    return results


# ============================================================================
# PAYMENT NOTIFICATIONS
# ============================================================================

def send_receipt_uploaded_notification(payment) -> bool:  # type: ignore
    """
    Уведомление риелтору о том, что гость загрузил квитанцию.
    Риелтор должен одобрить или отклонить платеж.
    """
    from apps.finances.models import Payment

    realtor = payment.booking.property.owner
    guest = payment.booking.guest

    subject = f"Новая квитанция по бронированию #{payment.booking.booking_code}"

    parsed_amount = payment.receipt_amount or 0
    expected_amount = payment.amount or 0
    amount_match = abs(parsed_amount - expected_amount) < 100  # Допуск 100 тенге

    html_message = f"""
    <html>
    <body>
        <h2>Здравствуйте, {realtor.first_name or realtor.username}!</h2>
        <p>Гость <strong>{guest.username or guest.email}</strong> загрузил квитанцию об оплате.</p>

        <h3>Детали:</h3>
        <ul>
            <li><strong>Бронирование:</strong> #{payment.booking.booking_code}</li>
            <li><strong>Объект:</strong> {payment.booking.property.title}</li>
            <li><strong>Ожидаемая сумма:</strong> {expected_amount} ₸</li>
            <li><strong>Сумма из квитанции:</strong> {parsed_amount} ₸</li>
            <li><strong>Совпадение:</strong> {"✅ Да" if amount_match else "⚠️ Проверьте внимательно"}</li>
        </ul>

        <p><strong>Требуется ваше решение:</strong></p>
        <p>Пожалуйста, проверьте квитанцию и одобрите или отклоните платеж в личном кабинете.</p>

        <p>С уважением,<br>Команда ЖильеGO</p>
    </body>
    </html>
    """

    # Email уведомление
    email_sent = send_email_notification(
        recipient_email=realtor.email,
        subject=subject,
        template_name=None,
        context={},
        html_message=html_message,
    )

    # In-app уведомление
    create_in_app_notification(
        user=realtor,
        title=subject,
        message=f"Гость {guest.username} загрузил квитанцию на {parsed_amount} ₸. Требуется ваше одобрение.",
    )

    # Telegram (stubbed)
    if realtor.telegram_id:
        send_telegram_notification(
            realtor.telegram_id,
            f"🔔 Новая квитанция!\n\n"
            f"Бронирование: #{payment.booking.booking_code}\n"
            f"Сумма: {parsed_amount} ₸ (ожидалось {expected_amount} ₸)\n"
            f"Проверьте и одобрите в личном кабинете.",
        )

    return email_sent


def send_payment_approved_notification(payment) -> bool:  # type: ignore
    """Уведомление гостю об одобрении платежа риелтором."""
    guest = payment.booking.guest

    subject = f"Платеж одобрен - бронирование #{payment.booking.booking_code}"

    html_message = f"""
    <html>
    <body>
        <h2>Здравствуйте, {guest.first_name or guest.username}!</h2>
        <p>Отличные новости! Ваш платеж одобрен риелтором.</p>

        <h3>Детали:</h3>
        <ul>
            <li><strong>Бронирование:</strong> #{payment.booking.booking_code}</li>
            <li><strong>Объект:</strong> {payment.booking.property.title}</li>
            <li><strong>Сумма:</strong> {payment.receipt_amount or payment.amount} ₸</li>
            <li><strong>Статус:</strong> ✅ Оплачено</li>
        </ul>

        {f"<p><strong>Комментарий риелтора:</strong> {payment.realtor_comment}</p>" if payment.realtor_comment else ""}

        <p>Теперь вы можете готовиться к заезду!</p>
        <p>Даты: {payment.booking.check_in.strftime('%d.%m.%Y')} - {payment.booking.check_out.strftime('%d.%m.%Y')}</p>

        <p>С уважением,<br>Команда ЖильеGO</p>
    </body>
    </html>
    """

    email_sent = send_email_notification(
        recipient_email=guest.email,
        subject=subject,
        template_name=None,
        context={},
        html_message=html_message,
    )

    create_in_app_notification(
        user=guest,
        title="Платеж одобрен!",
        message=f"Ваш платеж по бронированию #{payment.booking.booking_code} одобрен. Бронирование подтверждено!",
    )

    if guest.telegram_id:
        send_telegram_notification(
            guest.telegram_id,
            f"✅ Платеж одобрен!\n\n"
            f"Бронирование #{payment.booking.booking_code} подтверждено.\n"
            f"Ждем вас {payment.booking.check_in.strftime('%d.%m.%Y')}!",
        )

    return email_sent


def send_payment_rejected_notification(payment) -> bool:  # type: ignore
    """Уведомление гостю об отклонении платежа риелтором."""
    guest = payment.booking.guest

    subject = f"Платеж отклонен - бронирование #{payment.booking.booking_code}"

    html_message = f"""
    <html>
    <body>
        <h2>Здравствуйте, {guest.first_name or guest.username}!</h2>
        <p>К сожалению, ваш платеж был отклонен риелтором.</p>

        <h3>Детали:</h3>
        <ul>
            <li><strong>Бронирование:</strong> #{payment.booking.booking_code}</li>
            <li><strong>Объект:</strong> {payment.booking.property.title}</li>
            <li><strong>Сумма:</strong> {payment.receipt_amount or payment.amount} ₸</li>
            <li><strong>Статус:</strong> ❌ Отклонено</li>
        </ul>

        <p><strong>Причина отклонения:</strong></p>
        <p>{payment.realtor_comment or "Не указана"}</p>

        <p>Пожалуйста, свяжитесь с риелтором для уточнения деталей или загрузите корректную квитанцию.</p>

        <p>С уважением,<br>Команда ЖильеGO</p>
    </body>
    </html>
    """

    email_sent = send_email_notification(
        recipient_email=guest.email,
        subject=subject,
        template_name=None,
        context={},
        html_message=html_message,
    )

    create_in_app_notification(
        user=guest,
        title="Платеж отклонен",
        message=f"Ваш платеж по бронированию #{payment.booking.booking_code} отклонен. Причина: {payment.realtor_comment or 'Не указана'}",
    )

    if guest.telegram_id:
        send_telegram_notification(
            guest.telegram_id,
            f"❌ Платеж отклонен\n\n"
            f"Бронирование: #{payment.booking.booking_code}\n"
            f"Причина: {payment.realtor_comment or 'Не указана'}\n"
            f"Свяжитесь с риелтором для уточнения.",
        )

    return email_sent
