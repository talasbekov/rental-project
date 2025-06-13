from .. import settings
from twilio.rest import Client
import logging

logger = logging.getLogger(__name__)

# This is the same as send_whatsapp_message from views.py earlier.
# Consolidating it here.
def send_whatsapp_message(to_number_without_prefix, message_body):
    """
    Sends a WhatsApp message using Twilio.
    to_number_without_prefix should be the number without 'whatsapp:' prefix.
    """
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # Ensure from_ number is correctly formatted if it's not the sandbox default
        from_whatsapp_number = settings.TWILIO_WHATSAPP_NUMBER
        if not from_whatsapp_number.startswith('whatsapp:'):
            from_whatsapp_number = f'whatsapp:{from_whatsapp_number}'

        message = client.messages.create(
            body=message_body,
            from_=from_whatsapp_number,
            to=f'whatsapp:{to_number_without_prefix}' # Add 'whatsapp:' prefix for recipient
        )
        logger.info(f"Message sent to {to_number_without_prefix}: SID {message.sid}")
        return message.sid
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_number_without_prefix}: {e}")
        return None

# send_whatsapp_reply is not strictly needed if using MessagingResponse directly,
# but can be a utility if we want to send messages outside the TwiML response flow.
# For now, MessagingResponse is primary for replies.
