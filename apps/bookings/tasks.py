"""Celery tasks for the booking domain."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task  # type: ignore
from django.db import transaction  # type: ignore
from django.utils import timezone  # type: ignore

from .models import Booking
from .services import release_dates_for_booking

logger = logging.getLogger(__name__)


@shared_task
def schedule_hold_expiration(booking_id: int) -> None:
    """Отменяет бронирование, если оно не подтверждено в срок."""

    try:
        booking = Booking.objects.get(pk=booking_id)
    except Booking.DoesNotExist:
        return

    if booking.should_expire():
        booking.status = Booking.Status.EXPIRED
        booking.payment_status = Booking.PaymentStatus.FAILED
        booking.cancellation_source = Booking.CancellationSource.SYSTEM
        booking.cancelled_at = booking.expires_at
        booking.save(
            update_fields=[
                "status",
                "payment_status",
                "cancellation_source",
                "cancelled_at",
            ]
        )
        release_dates_for_booking(booking)


# ============================================================================
# PERIODIC TASKS (запускаются автоматически через Celery Beat)
# ============================================================================

@shared_task(name="bookings.expire_pending_bookings")
def expire_pending_bookings() -> dict[str, int]:
    """
    Автоматическая отмена просроченных броней.

    Ищет бронирования со статусом PENDING, у которых истек expires_at,
    и отменяет их автоматически.

    Запускается каждую минуту через Celery Beat.

    Returns:
        dict: {"expired": количество отмененных броней}
    """
    now = timezone.now()
    expired_count = 0

    # Находим просроченные брони
    expired_bookings = Booking.objects.filter(
        status=Booking.Status.PENDING,
        expires_at__lte=now,
    ).select_related("property", "guest")

    for booking in expired_bookings:
        try:
            with transaction.atomic():
                booking.status = Booking.Status.EXPIRED
                booking.payment_status = Booking.PaymentStatus.FAILED
                booking.cancellation_source = Booking.CancellationSource.SYSTEM
                booking.cancellation_reason = "Время на оплату истекло (15 минут)"
                booking.cancelled_at = now
                booking.save(
                    update_fields=[
                        "status",
                        "payment_status",
                        "cancellation_source",
                        "cancellation_reason",
                        "cancelled_at",
                    ]
                )

                # Освобождаем даты
                release_dates_for_booking(booking)

                # Отправляем уведомление гостю
                notify_booking_expired.delay(booking.id)

                expired_count += 1
                logger.info(
                    f"Booking {booking.booking_code} expired automatically. "
                    f"Guest: {booking.guest.email}, Property: {booking.property.title}"
                )
        except Exception as e:
            logger.error(f"Error expiring booking {booking.id}: {e}", exc_info=True)

    if expired_count > 0:
        logger.info(f"Expired {expired_count} pending bookings")

    return {"expired": expired_count}


@shared_task(name="bookings.update_in_progress_bookings")
def update_in_progress_bookings() -> dict[str, int]:
    """
    Автоматический перевод подтвержденных броней в статус IN_PROGRESS.

    Когда наступает дата заезда (check_in), бронирование переводится
    в статус IN_PROGRESS.

    Запускается каждый час.

    Returns:
        dict: {"updated": количество обновленных броней}
    """
    today = timezone.now().date()
    updated_count = 0

    # Находим подтвержденные брони, у которых сегодня дата заезда
    bookings_to_start = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        check_in=today,
    ).select_related("property", "guest")

    for booking in bookings_to_start:
        try:
            booking.status = Booking.Status.IN_PROGRESS
            booking.save(update_fields=["status"])

            # Отправляем welcome уведомление гостю
            notify_booking_started.delay(booking.id)

            updated_count += 1
            logger.info(f"Booking {booking.booking_code} started (IN_PROGRESS)")
        except Exception as e:
            logger.error(f"Error updating booking {booking.id} to IN_PROGRESS: {e}", exc_info=True)

    if updated_count > 0:
        logger.info(f"Updated {updated_count} bookings to IN_PROGRESS")

    return {"updated": updated_count}


@shared_task(name="bookings.complete_finished_bookings")
def complete_finished_bookings() -> dict[str, int]:
    """
    Автоматическое завершение броней после выезда.

    Когда наступает дата выезда (check_out), бронирование переводится
    в статус COMPLETED.

    Запускается каждый час.

    Returns:
        dict: {"completed": количество завершенных броней}
    """
    today = timezone.now().date()
    completed_count = 0

    # Находим активные брони, у которых сегодня или раньше дата выезда
    bookings_to_complete = Booking.objects.filter(
        status=Booking.Status.IN_PROGRESS,
        check_out__lte=today,
    ).select_related("property", "guest")

    for booking in bookings_to_complete:
        try:
            booking.status = Booking.Status.COMPLETED
            booking.save(update_fields=["status"])

            # Отправляем благодарность и просьбу оставить отзыв
            notify_booking_completed.delay(booking.id)

            completed_count += 1
            logger.info(f"Booking {booking.booking_code} completed")
        except Exception as e:
            logger.error(f"Error completing booking {booking.id}: {e}", exc_info=True)

    if completed_count > 0:
        logger.info(f"Completed {completed_count} bookings")

    return {"completed": completed_count}


@shared_task(name="bookings.send_upcoming_booking_reminders")
def send_upcoming_booking_reminders() -> dict[str, int]:
    """
    Отправка напоминаний о предстоящем заезде.

    За 24 часа до заезда гость получает напоминание с инструкциями.

    Запускается каждые 6 часов.

    Returns:
        dict: {"sent": количество отправленных напоминаний}
    """
    tomorrow = timezone.now().date() + timedelta(days=1)
    sent_count = 0

    # Находим подтвержденные брони с заездом завтра
    upcoming_bookings = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        check_in=tomorrow,
    ).select_related("property", "guest")

    for booking in upcoming_bookings:
        try:
            notify_booking_reminder.delay(booking.id)
            sent_count += 1
            logger.info(f"Sent reminder for booking {booking.booking_code}")
        except Exception as e:
            logger.error(f"Error sending reminder for booking {booking.id}: {e}", exc_info=True)

    if sent_count > 0:
        logger.info(f"Sent {sent_count} booking reminders")

    return {"sent": sent_count}


# ============================================================================
# NOTIFICATION TASKS
# ============================================================================

@shared_task(name="bookings.notify_booking_expired")
def notify_booking_expired(booking_id: int) -> bool:
    """Уведомление гостю об истечении времени оплаты."""
    try:
        booking = Booking.objects.select_related("guest", "property").get(id=booking_id)

        from apps.notifications.services import send_booking_expired_email, create_in_app_notification

        # Отправляем email
        send_booking_expired_email(booking)

        # Создаем in-app уведомление
        create_in_app_notification(
            user=booking.guest,
            title=f"Бронирование #{booking.booking_code} отменено",
            message=f"К сожалению, время на оплату истекло. Бронирование объекта {booking.property.title} отменено.",
        )

        logger.info(
            f"[NOTIFICATION] Booking expired notification sent: {booking.booking_code} "
            f"to guest {booking.guest.email}"
        )

        return True
    except Booking.DoesNotExist:
        logger.error(f"Booking {booking_id} not found for expiry notification")
        return False


@shared_task(name="bookings.notify_booking_confirmed")
def notify_booking_confirmed(booking_id: int) -> bool:
    """Уведомление гостю и риелтору об успешном бронировании."""
    try:
        booking = Booking.objects.select_related("guest", "property", "property__owner").get(id=booking_id)

        from apps.notifications.services import (
            send_booking_confirmation_email,
            send_new_booking_to_realtor_email,
            create_in_app_notification,
            send_telegram_booking_notification,
        )

        # Уведомление гостю
        send_booking_confirmation_email(booking)
        create_in_app_notification(
            user=booking.guest,
            title=f"Бронирование #{booking.booking_code} подтверждено!",
            message=f"Ваше бронирование {booking.property.title} на {booking.check_in.strftime('%d.%m.%Y')} подтверждено.",
        )

        # Уведомление риелтору
        send_new_booking_to_realtor_email(booking)
        send_telegram_booking_notification(booking.property.owner, booking)
        create_in_app_notification(
            user=booking.property.owner,
            title=f"Новое бронирование #{booking.booking_code}",
            message=f"Новое бронирование объекта {booking.property.title} на {booking.check_in.strftime('%d.%m.%Y')}.",
        )

        logger.info(
            f"[NOTIFICATION] Booking confirmed notifications sent: {booking.booking_code}"
        )

        return True
    except Booking.DoesNotExist:
        logger.error(f"Booking {booking_id} not found for confirmation notification")
        return False


@shared_task(name="bookings.notify_booking_started")
def notify_booking_started(booking_id: int) -> bool:
    """Welcome уведомление гостю в день заезда."""
    try:
        booking = Booking.objects.select_related("guest", "property").get(id=booking_id)

        logger.info(
            f"[NOTIFICATION] Welcome message for booking {booking.booking_code} "
            f"to guest {booking.guest.email}"
        )

        # TODO: Отправить инструкции по заселению с кодами доступа

        return True
    except Booking.DoesNotExist:
        logger.error(f"Booking {booking_id} not found for welcome notification")
        return False


@shared_task(name="bookings.notify_booking_completed")
def notify_booking_completed(booking_id: int) -> bool:
    """Благодарность гостю и просьба оставить отзыв."""
    try:
        booking = Booking.objects.select_related("guest", "property").get(id=booking_id)

        logger.info(
            f"[NOTIFICATION] Completion message for booking {booking.booking_code} "
            f"to guest {booking.guest.email}"
        )

        # TODO: Отправить благодарность и ссылку на отзыв

        return True
    except Booking.DoesNotExist:
        logger.error(f"Booking {booking_id} not found for completion notification")
        return False


@shared_task(name="bookings.notify_booking_reminder")
def notify_booking_reminder(booking_id: int) -> bool:
    """Напоминание за 24 часа до заезда."""
    try:
        booking = Booking.objects.select_related("guest", "property").get(id=booking_id)

        from apps.notifications.services import send_booking_reminder_email, create_in_app_notification

        # Отправляем напоминание
        send_booking_reminder_email(booking)
        create_in_app_notification(
            user=booking.guest,
            title="Напоминание о заезде завтра",
            message=f"Завтра ваш заезд в {booking.property.title}. Инструкции отправим утром.",
        )

        logger.info(
            f"[NOTIFICATION] Reminder sent for booking {booking.booking_code} "
            f"to guest {booking.guest.email}"
        )

        return True
    except Booking.DoesNotExist:
        logger.error(f"Booking {booking_id} not found for reminder notification")
        return False


@shared_task(name="bookings.notify_booking_cancelled")
def notify_booking_cancelled(booking_id: int) -> bool:
    """Уведомление об отмене бронирования."""
    try:
        booking = Booking.objects.select_related("guest", "property", "property__owner").get(id=booking_id)

        # Уведомление гостю
        logger.info(
            f"[NOTIFICATION] Booking cancelled: {booking.booking_code} "
            f"for guest {booking.guest.email}"
        )

        # Уведомление риелтору
        logger.info(
            f"[NOTIFICATION] Booking cancelled: {booking.booking_code} "
            f"for property owner {booking.property.owner.email}"
        )

        return True
    except Booking.DoesNotExist:
        logger.error(f"Booking {booking_id} not found for cancellation notification")
        return False
