import logging
from .utils import send_whatsapp_message
from booking_bot.bookings.models import Booking
from booking_bot.users.models import UserProfile # To get phone number if only user is available

logger = logging.getLogger(__name__)

def send_booking_confirmation_notification(booking_id):
    """
    Sends a notification when a booking is confirmed (e.g., after successful payment).
    """
    try:
        booking = Booking.objects.select_related('user', 'property', 'user__profile').get(id=booking_id)
        user_profile = booking.user.profile

        if not user_profile.phone_number:
            logger.warning(f"User {booking.user.username} has no phone number in profile for booking {booking_id}.")
            return

        message_body = (
            f"🎉 Booking Confirmed! 🎉\n"
            f"Your booking for {booking.property.name} (ID: {booking.id}) from "
            f"{booking.start_date.strftime('%Y-%m-%d')} to {booking.end_date.strftime('%Y-%m-%d')} "
            f"has been confirmed.\n"
            f"Total Price: {booking.total_price} KZT.\n"
            f"Status: {booking.status.capitalize()}."
        )
        send_whatsapp_message(user_profile.phone_number.replace('whatsapp:', ''), message_body)
        logger.info(f"Sent booking confirmation for booking ID {booking_id} to {user_profile.phone_number}")
    except Booking.DoesNotExist:
        logger.error(f"Cannot send confirmation: Booking ID {booking_id} not found.")
    except UserProfile.DoesNotExist: # Should not happen if user has a booking
        logger.error(f"Cannot send confirmation: UserProfile for user {booking.user.username} not found for booking {booking_id}.")
    except Exception as e:
        logger.error(f"Error sending booking confirmation for {booking_id}: {e}", exc_info=True)

def send_payment_failed_notification(booking_id, reason=""):
    """
    Sends a notification when a payment for a booking fails.
    """
    try:
        booking = Booking.objects.select_related('user', 'property', 'user__profile').get(id=booking_id)
        user_profile = booking.user.profile

        if not user_profile.phone_number:
            logger.warning(f"User {booking.user.username} has no phone number in profile for booking {booking_id}.")
            return

        message_body = (
            f"⚠️ Payment Failed ⚠️\n"
            f"Unfortunately, the payment for your booking for {booking.property.name} (ID: {booking.id}) failed."
        )
        if reason:
            message_body += f" Reason: {reason}."
        message_body += f"\nPlease try paying again using: /pay {booking.id}" # Corrected variable access

        send_whatsapp_message(user_profile.phone_number.replace('whatsapp:', ''), message_body)
        logger.info(f"Sent payment failed notification for booking ID {booking_id} to {user_profile.phone_number}")
    except Booking.DoesNotExist:
        logger.error(f"Cannot send payment failed notification: Booking ID {booking_id} not found.")
    except UserProfile.DoesNotExist:
        logger.error(f"Cannot send payment failed notification: UserProfile for user {booking.user.username} not found for booking {booking_id}.")
    except Exception as e:
        logger.error(f"Error sending payment failed notification for {booking_id}: {e}", exc_info=True)

def send_booking_cancelled_notification(booking_id, cancelled_by_user=True):
    """
    Sends a notification when a booking is cancelled.
    This is separate from the direct command response if cancellation happens asynchronously
    or by an admin. For user-initiated cancellation via bot, the direct response in handlers.py is often sufficient.
    """
    try:
        booking = Booking.objects.select_related('user', 'property', 'user__profile').get(id=booking_id)
        user_profile = booking.user.profile

        if not user_profile.phone_number:
            logger.warning(f"User {booking.user.username} has no phone number in profile for booking {booking_id}.")
            return

        by_whom = "by you" if cancelled_by_user else "by an administrator"
        message_body = (
            f"Booking Cancelled\n"
            f"Your booking for {booking.property.name} (ID: {booking.id}) from "
            f"{booking.start_date.strftime('%Y-%m-%d')} to {booking.end_date.strftime('%Y-%m-%d')} "
            f"has been cancelled {by_whom}."
        )
        send_whatsapp_message(user_profile.phone_number.replace('whatsapp:', ''), message_body)
        logger.info(f"Sent booking cancellation notification for booking ID {booking_id} to {user_profile.phone_number}")
    except Booking.DoesNotExist:
        logger.error(f"Cannot send cancellation notification: Booking ID {booking_id} not found.")
    except UserProfile.DoesNotExist:
        logger.error(f"Cannot send cancellation notification: UserProfile for user {booking.user.username} not found for booking {booking_id}.")
    except Exception as e:
        logger.error(f"Error sending booking cancellation for {booking_id}: {e}", exc_info=True)
