import os

from celery import Celery
from celery.schedules import crontab  # type: ignore

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("rental_project")

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# ============================================================================
# CELERY BEAT SCHEDULE (Periodic Tasks)
# ============================================================================

app.conf.beat_schedule = {
    # Отмена просроченных броней - каждую минуту
    "expire-pending-bookings": {
        "task": "bookings.expire_pending_bookings",
        "schedule": 60.0,  # каждые 60 секунд
        "options": {"expires": 50},
    },
    # Перевод броней в статус IN_PROGRESS - каждый час
    "update-in-progress-bookings": {
        "task": "bookings.update_in_progress_bookings",
        "schedule": crontab(minute=0),  # каждый час в начале часа
    },
    # Завершение броней после выезда - каждый час
    "complete-finished-bookings": {
        "task": "bookings.complete_finished_bookings",
        "schedule": crontab(minute=15),  # каждый час в 15 минут
    },
    # Напоминания о предстоящем заезде - каждые 6 часов
    "send-upcoming-booking-reminders": {
        "task": "bookings.send_upcoming_booking_reminders",
        "schedule": crontab(minute=0, hour="*/6"),  # каждые 6 часов
    },
}

app.conf.timezone = "Asia/Almaty"
