from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import logging

logger = logging.getLogger(__name__)

def send_whatsapp_message(to_number, message_body):
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=message_body,
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            to=f'whatsapp:{to_number}' # Ensure 'whatsapp:' prefix for recipient
        )
        logger.info(f"Message sent to {to_number}: SID {message.sid}")
        return message.sid
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_number}: {e}")
        return None

@csrf_exempt # Twilio webhooks do not send CSRF tokens
def twilio_webhook(request):
    if request.method == 'POST':
        incoming_msg = request.POST.get('Body', '').lower()
        from_number = request.POST.get('From', '').replace('whatsapp:', '') # Get sender number

        logger.info(f"Incoming message from {from_number}: {incoming_msg}")

        # Simple echo bot for now
        response = MessagingResponse()
        response.message(f"You said: {incoming_msg}")

        # Example of using the send_whatsapp_message utility (can be removed for echo)
        # send_whatsapp_message(from_number, f"Thanks for your message: '{incoming_msg}'")

        return HttpResponse(str(response), content_type='application/xml')

    return HttpResponse("Not a POST request", status=405)
