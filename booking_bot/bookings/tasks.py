# booking_bot/bookings/tasks.py - Celery задачи для автоматической отмены

from celery import shared_task
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@shared_task
def cancel_expired_booking(booking_id):
    """Автоматическая отмена неоплаченного бронирования"""
    from booking_bot.bookings.models import Booking

    try:
        booking = Booking.objects.get(id=booking_id)

        # Проверяем, что бронирование все еще в статусе ожидания оплаты
        if booking.status == 'pending_payment':
            if booking.expires_at and datetime.now() >= booking.expires_at:
                booking.status = 'cancelled'
                booking.cancel_reason = 'Истекло время оплаты'
                booking.cancelled_at = datetime.now()
                booking.save()

                logger.info(f"Booking {booking_id} auto-cancelled due to payment timeout")

                # Отправляем уведомление пользователю
                from booking_bot.telegram_bot.utils import send_telegram_message
                if hasattr(booking.user, 'profile') and booking.user.profile.telegram_chat_id:
                    send_telegram_message(
                        booking.user.profile.telegram_chat_id,
                        f"❌ Бронирование #{booking_id} отменено из-за неоплаты.\n"
                        f"Квартира снова доступна для бронирования."
                    )

    except Booking.DoesNotExist:
        logger.warning(f"Booking {booking_id} not found for cancellation")
    except Exception as e:
        logger.error(f"Error cancelling expired booking {booking_id}: {e}")


@shared_task
def check_all_expired_bookings():
    """Периодическая проверка всех истекших бронирований"""
    from booking_bot.bookings.models import Booking

    expired_bookings = Booking.objects.filter(
        status='pending_payment',
        expires_at__lt=datetime.now()
    )

    for booking in expired_bookings:
        cancel_expired_booking.delay(booking.id)

    logger.info(f"Found and scheduled cancellation for {expired_bookings.count()} expired bookings")
