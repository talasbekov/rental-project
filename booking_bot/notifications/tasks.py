# booking_bot/notifications/tasks.py - Celery задачи

from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def process_notification_queue():
    """Периодическая обработка очереди уведомлений"""
    from .service import NotificationService

    NotificationService.process_queue()
    logger.info("Processed notification queue")


@shared_task
def send_checkin_reminders():
    """Отправка напоминаний о заезде"""
    from booking_bot.bookings.models import Booking
    from .service import NotificationService
    from datetime import date, timedelta

    # Напоминания за день до заезда
    tomorrow = date.today() + timedelta(days=1)

    bookings = Booking.objects.filter(
        start_date=tomorrow,
        status='confirmed'
    ).select_related('property', 'user')

    for booking in bookings:
        NotificationService.schedule(
            event='checkin_reminder',
            user=booking.user,
            context={
                'booking': booking,
                'property': booking.property,
                'checkin_date': booking.start_date.strftime('%d.%m.%Y'),
                'property_name': booking.property.name,
                'address': booking.property.address,
            }
        )

    logger.info(f"Scheduled {bookings.count()} checkin reminders")


@shared_task
def monitor_low_occupancy():
    """Мониторинг низкой загрузки"""
    from booking_bot.listings.models import Property, PropertyCalendarManager
    from .service import NotificationService
    from datetime import date, timedelta

    # Проверяем загрузку за последний месяц
    start_date = date.today() - timedelta(days=30)
    end_date = date.today()

    properties = Property.objects.filter(status='Свободна')

    for property_obj in properties:
        occupancy = PropertyCalendarManager.get_occupancy_rate(
            property_obj, start_date, end_date
        )

        if occupancy < 40:  # Порог 40%
            NotificationService.schedule(
                event='low_occupancy',
                user=property_obj.owner,
                context={
                    'property': property_obj,
                    'property_name': property_obj.name,
                    'occupancy_rate': round(occupancy, 1),
                    'period': '30 дней',
                }
            )

    logger.info(f"Checked occupancy for {properties.count()} properties")
