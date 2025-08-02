# booking_bot/whatsapp_bot/tasks.py

from celery import shared_task
from django.conf import settings
from datetime import datetime, timedelta
import logging

from booking_bot.bookings.models import Booking
from booking_bot.users.models import UserProfile
from .utils import send_whatsapp_message, send_whatsapp_button_message

logger = logging.getLogger(__name__)


@shared_task
def send_booking_reminder(booking_id):
    """Отправить напоминание о предстоящем заезде"""
    try:
        booking = Booking.objects.get(id=booking_id)
        profile = UserProfile.objects.filter(user=booking.user).first()

        if not profile or not profile.whatsapp_phone:
            logger.warning(f"No WhatsApp phone for booking {booking_id}")
            return

        days_until = (booking.start_date - datetime.now().date()).days

        text = (
            f"🔔 *Напоминание о бронировании*\n\n"
            f"Через {days_until} дн. у вас заезд:\n"
            f"🏠 {booking.property.name}\n"
            f"📅 Заезд: {booking.start_date.strftime('%d.%m.%Y')}\n"
            f"📍 Адрес: {booking.property.address}\n"
        )

        if booking.property.digital_lock_code:
            text += f"\n🔐 Код от замка: {booking.property.digital_lock_code}"

        buttons = [
            {"id": f"booking_details_{booking_id}", "title": "📋 Детали"},
            {"id": "contact_owner", "title": "📞 Связаться"},
            {"id": "main_menu", "title": "🏠 Меню"}
        ]

        send_whatsapp_button_message(
            profile.whatsapp_phone,
            text,
            buttons,
            header="Напоминание"
        )

        logger.info(f"Sent booking reminder for {booking_id}")

    except Exception as e:
        logger.error(f"Error sending booking reminder: {e}")


@shared_task
def send_review_request(booking_id):
    """Запросить отзыв после выезда"""
    try:
        booking = Booking.objects.get(id=booking_id)
        profile = UserProfile.objects.filter(user=booking.user).first()

        if not profile or not profile.whatsapp_phone:
            return

        # Проверяем, что выезд был вчера
        if booking.end_date != datetime.now().date() - timedelta(days=1):
            return

        text = (
            f"👋 Добрый день!\n\n"
            f"Надеемся, вам понравилось проживание в:\n"
            f"🏠 {booking.property.name}\n\n"
            f"Поделитесь своим мнением - это поможет другим гостям!"
        )

        buttons = [
            {"id": f"leave_review_{booking_id}", "title": "✍️ Оставить отзыв"},
            {"id": "skip_review", "title": "⏭️ Пропустить"}
        ]

        send_whatsapp_button_message(
            profile.whatsapp_phone,
            text,
            buttons,
            header="Оцените проживание"
        )

    except Exception as e:
        logger.error(f"Error sending review request: {e}")


@shared_task
def notify_owner_new_booking(booking_id):
    """Уведомить владельца о новом бронировании"""
    try:
        booking = Booking.objects.select_related(
            'property__owner__profile'
        ).get(id=booking_id)

        owner_profile = booking.property.owner.profile
        if not owner_profile.whatsapp_phone:
            return

        text = (
            f"🎉 *Новое бронирование!*\n\n"
            f"🏠 {booking.property.name}\n"
            f"👤 Гость: {booking.user.get_full_name() or booking.user.username}\n"
            f"📅 {booking.start_date.strftime('%d.%m')} - "
            f"{booking.end_date.strftime('%d.%m.%Y')}\n"
            f"💰 Сумма: {booking.total_price:,.0f} ₸\n"
        )

        if hasattr(booking.user, 'profile') and booking.user.profile.phone_number:
            text += f"📞 Телефон: {booking.user.profile.phone_number}"

        send_whatsapp_message(owner_profile.whatsapp_phone, text)

    except Exception as e:
        logger.error(f"Error notifying owner: {e}")


@shared_task
def send_payment_confirmation(booking_id):
    """Отправить подтверждение оплаты"""
    try:
        booking = Booking.objects.get(id=booking_id)
        profile = UserProfile.objects.filter(user=booking.user).first()

        if not profile or not profile.whatsapp_phone:
            return

        from .handlers import send_booking_confirmation
        send_booking_confirmation(profile.whatsapp_phone, booking)

    except Exception as e:
        logger.error(f"Error sending payment confirmation: {e}")


@shared_task
def check_expired_bookings():
    """Проверить и отменить неоплаченные бронирования"""
    expired_time = datetime.now() - timedelta(minutes=15)

    expired_bookings = Booking.objects.filter(
        status='pending_payment',
        created_at__lt=expired_time
    )

    for booking in expired_bookings:
        booking.status = 'cancelled'
        booking.save()

        # Уведомляем пользователя
        profile = UserProfile.objects.filter(user=booking.user).first()
        if profile and profile.whatsapp_phone:
            send_whatsapp_message(
                profile.whatsapp_phone,
                f"❌ Бронирование #{booking.id} отменено из-за неоплаты.\n"
                f"Квартира снова доступна для бронирования."
            )

        logger.info(f"Cancelled expired booking {booking.id}")

# Настройка периодических задач в settings.py:
# from celery.schedules import crontab
#
# CELERY_BEAT_SCHEDULE = {
#     'check-expired-bookings': {
#         'task': 'booking_bot.whatsapp_bot.tasks.check_expired_bookings',
#         'schedule': crontab(minute='*/5'),  # каждые 5 минут
#     },
#     'send-booking-reminders': {
#         'task': 'booking_bot.whatsapp_bot.tasks.send_daily_reminders',
#         'schedule': crontab(hour=10, minute=0),  # каждый день в 10:00
#     },
# }
