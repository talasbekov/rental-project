import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404 # For cleaner object retrieval

from booking_bot.bookings.models import Booking
from booking_bot.users.models import UserProfile
# Assuming send_whatsapp_message is a utility function you've created
# from booking_bot.whatsapp_bot.utils import send_whatsapp_message
# For now, we'll mock it or log instead of sending actual messages if utils isn't ready
from booking_bot.whatsapp_bot.handlers import clear_user_state


logger = logging.getLogger(__name__)

# Mock function if actual WhatsApp sending utility is not yet available or for testing
def send_whatsapp_message(phone_number, message_body):
    logger.info(f"MOCK WHATSAPP to {phone_number}: {message_body}")
    # In a real scenario, this would integrate with Twilio or another WhatsApp provider
    # For example:
    # from twilio.rest import Client
    # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    # message = client.messages.create(
    #     body=message_body,
    #     from_=settings.TWILIO_WHATSAPP_NUMBER,
    #     to=f'whatsapp:{phone_number}'
    # )
    # logger.info(f"Sent WhatsApp message SID: {message.sid} to {phone_number}")
    pass


@csrf_exempt
def kaspi_payment_webhook(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info(f"Kaspi webhook received data: {data}")
        except json.JSONDecodeError:
            logger.error("Kaspi webhook: Invalid JSON received.")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        # Extract identifiers and status - adjust keys based on actual Kaspi API
        # Common practice is that Kaspi sends its own transaction ID back.
        # We assume 'invoice_id' or 'order_id' might be what we passed to Kaspi.
        # For this implementation, we'll rely on 'kaspi_payment_id' which we stored.

        kaspi_internal_id = data.get('transactionId') # This is what Kaspi's own service in kaspi_service.py returns as 'payment_id'
        # our_booking_id_from_kaspi = data.get('orderId') # If Kaspi returns the ID we sent it
        payment_status = data.get('status') # e.g., 'COMPLETED', 'FAILED', 'PAID', 'SUCCESS'

        if not kaspi_internal_id:
            logger.error(f"Kaspi webhook: 'transactionId' (kaspi_payment_id) not found in payload: {data}")
            return JsonResponse({'status': 'error', 'message': "'transactionId' is required"}, status=400)

        if not payment_status:
            logger.error(f"Kaspi webhook: 'status' not found in payload for kaspi_payment_id {kaspi_internal_id}: {data}")
            return JsonResponse({'status': 'error', 'message': "'status' is required"}, status=400)

        try:
            # Primary lookup using the kaspi_payment_id we stored
            booking = Booking.objects.get(kaspi_payment_id=kaspi_internal_id)
        except Booking.DoesNotExist:
            logger.error(f"Kaspi webhook: Booking not found for kaspi_payment_id: {kaspi_internal_id}")
            # Optionally, if Kaspi also returns the booking.id we sent as 'orderId' or similar:
            # our_booking_id = data.get('orderId')
            # if our_booking_id:
            #     try:
            #         booking = Booking.objects.get(id=our_booking_id)
            #     except Booking.DoesNotExist:
            #         logger.error(f"Kaspi webhook: Booking also not found for internal ID: {our_booking_id}")
            #         return JsonResponse({'status': 'error', 'message': 'Booking not found'}, status=404)
            # else:
            return JsonResponse({'status': 'error', 'message': 'Booking not found with provided kaspi_payment_id'}, status=404)
        except Exception as e: # Other potential errors during lookup
            logger.error(f"Kaspi webhook: Error retrieving booking for kaspi_payment_id {kaspi_internal_id}: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': 'Error retrieving booking'}, status=500)


        # Process Payment Status (Kaspi's actual status values might differ)
        # Based on kaspi_service.py, it seems 'SUCCESS' is used for successful payment.
        if payment_status.upper() == 'SUCCESS': # Adjust to actual Kaspi status for success
            if booking.status == 'confirmed':
                logger.info(f"Kaspi webhook: Booking {booking.id} is already confirmed. Ignoring duplicate success notification.")
            else:
                booking.status = 'confirmed'
                booking.save()
                logger.info(f"Booking {booking.id} confirmed via Kaspi webhook (kaspi_payment_id: {kaspi_internal_id}).")

                try:
                    user_profile = UserProfile.objects.get(user=booking.user)
                    property_details = booking.property

                    message_to_user = (
                        f"Payment confirmed for your booking of '{property_details.name}'!\n"
                        f"Booking ID: {booking.id}\n"
                        f"Dates: {booking.start_date.strftime('%Y-%m-%d')} to {booking.end_date.strftime('%Y-%m-%d')}\n"
                        f"Address: {property_details.address}\n"
                    )

                    access_info = property_details.digital_lock_code or property_details.key_safe_code
                    if access_info:
                        message_to_user += f"Access Code: {access_info}\n"

                    if property_details.entry_instructions:
                        message_to_user += f"Entry Instructions: {property_details.entry_instructions}"
                    elif access_info: # Default instruction if specific one is missing but code exists
                         message_to_user += "Use the access code on the door/key safe."
                    else: # No code, no instructions
                        message_to_user += "Please contact support for entry instructions if not provided separately."


                    send_whatsapp_message(user_profile.phone_number, message_to_user)

                    # Clear user's state in the bot after successful booking & notification
                    clear_user_state(user_profile)
                    logger.info(f"Sent confirmation WhatsApp to {user_profile.phone_number} and cleared state for booking {booking.id}.")

                except UserProfile.DoesNotExist:
                    logger.error(f"UserProfile not found for user {booking.user.id} associated with booking {booking.id}. Cannot send WhatsApp confirmation.")
                except Exception as e:
                    logger.error(f"Error sending WhatsApp confirmation or clearing state for booking {booking.id}: {e}", exc_info=True)
                    # The booking is confirmed, but notification failed. This needs monitoring.

        elif payment_status.upper() == 'FAILED': # Adjust to actual Kaspi status for failure
            if booking.status != 'confirmed': # Don't revert a confirmed booking due to a late failure message
                booking.status = 'payment_failed'
                booking.save()
                logger.warning(f"Booking {booking.id} payment failed via Kaspi webhook (kaspi_payment_id: {kaspi_internal_id}). Status set to 'payment_failed'.")
                # Optionally, notify user of failure if desired (might be noisy if they retry)
                # user_profile = UserProfile.objects.get(user=booking.user)
                # send_whatsapp_message(user_profile.phone_number, f"Payment for booking ID {booking.id} ({booking.property.name}) failed. Please try booking again or contact support.")
            else:
                logger.warning(f"Kaspi webhook: Received FAILED status for already confirmed booking {booking.id}. Ignored.")

        else:
            logger.info(f"Kaspi webhook: Received unhandled status '{payment_status}' for booking {booking.id} (kaspi_payment_id: {kaspi_internal_id}). Current booking status: {booking.status}.")
            # Potentially handle other statuses if Kaspi has them (e.g., PENDING, TIMEOUT, etc.)

        return JsonResponse({'status': 'success', 'message': 'Webhook processed'}, status=200)

    else:
        logger.warning("Kaspi webhook: Received non-POST request.")
        return HttpResponse("Method not allowed", status=405)

# Example of how you might have a simple Payment model if you weren't updating Booking directly
# from django.db import models
# class Payment(models.Model):
#     booking = models.ForeignKey(Booking, on_delete=models.CASCADE)
#     kaspi_payment_id = models.CharField(max_length=255, unique=True)
#     status = models.CharField(max_length=50) # e.g., 'pending', 'successful', 'failed'
#     amount = models.DecimalField(max_digits=10, decimal_places=2)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     def __str__(self):
#         return f"Payment {self.kaspi_payment_id} for Booking {self.booking.id} - {self.status}"
