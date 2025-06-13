from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property
from booking_bot.bookings.models import Booking
from unittest.mock import patch, MagicMock
import json
from datetime import date, timedelta

# Ensure this path is correct based on your project structure
# It's used to mock functions within your payments.views module
VIEWS_MODULE_PATH = 'booking_bot.payments.views'

class PaymentsWebhookTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.super_user = User.objects.create_superuser(username='superadmin', password='password') # For property owner
        self.user = User.objects.create_user(username='webhookuser', password='password')
        self.user_profile = UserProfile.objects.create(user=self.user, phone_number='+1987654321', whatsapp_state={})

        # Create a property - ensure all required fields are provided
        self.property = Property.objects.create(
            name="Test Prop Webhook",
            number_of_rooms=1,
            price_per_day=100,
            owner=self.super_user, # Assuming owner must be an admin or superuser
            region="Yesil District", # Ensure this is a valid choice if choices are enforced
            status="available",      # Ensure this is a valid choice
            address="123 Test St",
            area=50 # Assuming area is required
        )

        # Create a booking that is pending payment
        self.booking = Booking.objects.create(
            user=self.user,
            property=self.property,
            status='pending_payment', # Ensure this status is valid
            start_date=date.today(),
            end_date=date.today() + timedelta(days=1),
            total_price=100,
            kaspi_payment_id='kaspi_test_123' # Pre-assign for lookup by webhook
        )

        # Ensure the URL name matches what's in your payments/urls.py
        # If it's namespaced, it would be 'payments:kaspi_payment_webhook'
        self.webhook_url = reverse('kaspi_payment_webhook')

    @patch(f'{VIEWS_MODULE_PATH}.send_whatsapp_message') # Patch the send_whatsapp_message in views.py
    @patch(f'{VIEWS_MODULE_PATH}.clear_user_state')    # Patch clear_user_state in views.py
    def test_kaspi_webhook_success(self, mock_clear_user_state, mock_send_whatsapp_message):
        payload = {
            "transactionId": "kaspi_test_123", # This should match booking.kaspi_payment_id
            "status": "SUCCESS", # Assuming Kaspi sends 'SUCCESS'
            # Add any other fields Kaspi might send that your webhook expects or logs
        }

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        json_response = response.json()
        self.assertEqual(json_response.get('status'), 'success')

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'confirmed')

        mock_send_whatsapp_message.assert_called_once()
        # Example: check part of the message content if needed
        args, kwargs = mock_send_whatsapp_message.call_args
        # args[0] is phone_number, args[1] is message_body
        self.assertEqual(args[0], self.user_profile.phone_number)
        self.assertIn("Payment confirmed for your booking", args[1])
        self.assertIn(self.property.name, args[1])

        mock_clear_user_state.assert_called_once_with(self.user_profile)

    @patch(f'{VIEWS_MODULE_PATH}.send_whatsapp_message')
    @patch(f'{VIEWS_MODULE_PATH}.clear_user_state')
    def test_kaspi_webhook_failure_status(self, mock_clear_user_state, mock_send_whatsapp_message):
        payload = {
            "transactionId": "kaspi_test_123",
            "status": "FAILED"
        }
        response = self.client.post(
            self.webhook_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200) # Webhook should still acknowledge
        json_response = response.json()
        self.assertEqual(json_response.get('status'), 'success') # Webhook processed it successfully

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'payment_failed')

        mock_send_whatsapp_message.assert_not_called() # No success message on failure
        mock_clear_user_state.assert_not_called()   # State not cleared on failure typically

    def test_kaspi_webhook_invalid_json(self):
        response = self.client.post(
            self.webhook_url,
            data="not json",
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        json_response = response.json()
        self.assertEqual(json_response.get('status'), 'error')
        self.assertEqual(json_response.get('message'), 'Invalid JSON')

    def test_kaspi_webhook_missing_transaction_id(self):
        payload = {"status": "SUCCESS"}
        response = self.client.post(
            self.webhook_url, data=json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        json_response = response.json()
        self.assertEqual(json_response.get('message'), "'transactionId' is required")

    def test_kaspi_webhook_booking_not_found(self):
        payload = {
            "transactionId": "non_existent_kaspi_id",
            "status": "SUCCESS"
        }
        response = self.client.post(
            self.webhook_url, data=json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)
        json_response = response.json()
        self.assertEqual(json_response.get('message'), 'Booking not found with provided kaspi_payment_id')

    def test_kaspi_webhook_method_not_allowed(self):
        response = self.client.get(self.webhook_url) # Use GET instead of POST
        self.assertEqual(response.status_code, 405)
        self.assertIn("Method not allowed", response.content.decode())

    @patch(f'{VIEWS_MODULE_PATH}.send_whatsapp_message')
    @patch(f'{VIEWS_MODULE_PATH}.clear_user_state')
    def test_kaspi_webhook_duplicate_success_notification(self, mock_clear_user_state, mock_send_whatsapp_message):
        # First, confirm the booking
        self.booking.status = 'confirmed'
        self.booking.save()

        payload = {
            "transactionId": "kaspi_test_123",
            "status": "SUCCESS"
        }
        response = self.client.post(
            self.webhook_url, data=json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        # Ensure WhatsApp message and clear_state were not called again
        mock_send_whatsapp_message.assert_not_called()
        mock_clear_user_state.assert_not_called()
        # Booking status should remain 'confirmed'
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'confirmed')

# Add more tests for other scenarios:
# - Different Kaspi statuses if your webhook handles more than SUCCESS/FAILED.
# - Error handling within the success block (e.g., UserProfile.DoesNotExist).
# - What happens if kaspi_payment_id is missing from the payload.
# - Test with alternative booking lookup (e.g., if Kaspi returns your internal booking ID).
```
