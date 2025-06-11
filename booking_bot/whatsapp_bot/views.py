from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from twilio.twiml.messaging_response import MessagingResponse
from booking_bot.users.models import UserProfile
# from .utils import send_whatsapp_message # Keep if needed for proactive messages
from .handlers import handle_unknown_user, handle_known_user
import logging

logger = logging.getLogger(__name__)

@csrf_exempt # Twilio webhooks do not send CSRF tokens
def twilio_webhook(request):
    if request.method == 'POST':
        incoming_msg_body = request.POST.get('Body', '').strip()
        from_number_raw = request.POST.get('From', '') # e.g., 'whatsapp:+1234567890'

        # Normalize from_number to be just the number, e.g., '+1234567890'
        from_number = from_number_raw.replace('whatsapp:', '')

        logger.info(f"Incoming message from {from_number} (raw: {from_number_raw}): {incoming_msg_body}")

        response_twiml = MessagingResponse()

        try:
            user_profile = UserProfile.objects.select_related('user').get(phone_number=from_number)
            # User is known
            handle_known_user(user_profile, incoming_msg_body, response_twiml)
        except UserProfile.DoesNotExist:
            # User is unknown, initiate registration or guide them
            handle_unknown_user(from_number, incoming_msg_body, response_twiml)
        except Exception as e:
            logger.error(f"Error processing webhook for {from_number}: {e}", exc_info=True)
            response_twiml.message("An internal error occurred. Please try again later.")

        return HttpResponse(str(response_twiml), content_type='application/xml')

    return HttpResponse("HTTP Method Not Allowed", status=405)

# The old send_whatsapp_message function is now in utils.py
# from django.conf import settings
# from twilio.rest import Client
# def send_whatsapp_message(to_number, message_body): ... (removed from here)
