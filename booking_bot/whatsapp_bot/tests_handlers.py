from django.test import TestCase
from django.contrib.auth.models import User
from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property  # Added for potential future tests
from booking_bot.bookings.models import Booking  # Added for potential future tests
from booking_bot.whatsapp_bot.handlers import (
    send_welcome_message,
    get_user_state,
    set_user_state,  # Added set_user_state
    handle_known_user,
    ACTION_MAIN_MENU,
    ACTION_SELECTING_REGION,
    BUTTON_SEARCH_APARTMENTS,
    REGIONS,  # _send_message_with_buttons (private, usually tested via public methods)
)
from twilio.twiml.messaging_response import MessagingResponse
import json
from unittest.mock import patch, MagicMock  # Added MagicMock

# Mock kaspi_initiate_payment if any part of handlers calls it directly (not in current examples)
# @patch('booking_bot.payments.kaspi_service.initiate_payment', return_value={'checkout_url': 'http://mockurl', 'payment_id': 'mock_kaspi_id'})
# Mock send_whatsapp_message at the module level where it's defined if it's a global utility
# For handlers, it's often passed or imported, so direct patching might be needed per test or class.


class HandlersWelcomeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.user_profile = UserProfile.objects.create(
            user=self.user, phone_number="+1234567890", whatsapp_state={}
        )

    def test_send_welcome_message(self):
        response_twiml = MessagingResponse()
        send_welcome_message(self.user_profile, response_twiml)

        # Check state
        self.user_profile.refresh_from_db()  # Ensure state is fresh if saved in function
        state = get_user_state(self.user_profile)
        self.assertEqual(state["action"], ACTION_MAIN_MENU)

        # Check TwiML response (simplified check)
        response_str = str(response_twiml)
        self.assertIn("Welcome to Daily Apartment Rentals Bot!", response_str)
        self.assertIn(
            BUTTON_SEARCH_APARTMENTS, response_str
        )  # Check if button text is in the message
        # Check for numbered button if _send_message_with_buttons formats it that way
        self.assertIn(f"1. {BUTTON_SEARCH_APARTMENTS}", response_str)


class HandlersRegionSelectionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser2", password="password")
        self.user_profile = UserProfile.objects.create(
            user=self.user, phone_number="+1234567892"
        )
        # Set initial state to main menu
        set_user_state(self.user_profile, ACTION_MAIN_MENU)  # Use our helper

    # Patch the specific function that would be called and is responsible for sending the next message/setting state
    @patch("booking_bot.whatsapp_bot.handlers.send_region_selection")
    def test_handle_known_user_clicks_search_apartments(
        self, mock_send_region_selection
    ):
        response_twiml = MessagingResponse()

        # Simulate user sending the button text for "Search Available Apartments"
        # In the handler, "1" would be mapped to BUTTON_SEARCH_APARTMENTS if action is ACTION_MAIN_MENU
        handle_known_user(
            self.user_profile, "1", response_twiml
        )  # "1" should map to the button

        mock_send_region_selection.assert_called_once_with(
            self.user_profile, response_twiml
        )

        # To test the state change by send_region_selection, you'd test send_region_selection directly:

    @patch(
        "booking_bot.whatsapp_bot.handlers._send_message_with_buttons"
    )  # Mock the actual message sending
    def test_send_region_selection_sets_state_and_sends_message(
        self, mock_send_msg_with_buttons
    ):
        response_twiml = MagicMock(spec=MessagingResponse)  # Use MagicMock for TwiML

        # Call the function directly
        from booking_bot.whatsapp_bot.handlers import (
            send_region_selection,
        )  # Local import for clarity

        send_region_selection(self.user_profile, response_twiml)

        self.user_profile.refresh_from_db()
        state = get_user_state(self.user_profile)
        self.assertEqual(state["action"], ACTION_SELECTING_REGION)

        # Check that _send_message_with_buttons was called with correct parameters
        mock_send_msg_with_buttons.assert_called_once()
        args, _ = mock_send_msg_with_buttons.call_args
        self.assertEqual(
            args[0], response_twiml
        )  # First arg is twilio_messaging_response
        self.assertIn("Please select a region:", args[1])  # Second arg is body
        self.assertEqual(args[2], REGIONS)  # Third arg is button_texts


# Add more test classes and methods for other parts of handlers.py following similar patterns:
# - Test individual state transition functions (like send_room_count_selection, etc.)
# - Test handle_known_user for different states and inputs (button clicks, text commands)
# - Mock external dependencies like database queries if focusing purely on logic,
#   or set up specific DB states if testing integration with DB.
# - Use @patch for functions that trigger side effects you don't want in the current unit test
#   (e.g., actual Twilio calls, calls to other complex functions that are tested separately).


# Example for testing ACTION_SELECTING_REGION state
class HandlersRoomSelectionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser3", password="password")
        self.user_profile = UserProfile.objects.create(
            user=self.user, phone_number="+1234567893"
        )
        set_user_state(self.user_profile, ACTION_SELECTING_REGION)

    @patch("booking_bot.whatsapp_bot.handlers.send_room_count_selection")
    def test_handle_known_user_selects_region(self, mock_send_room_count_selection):
        response_twiml = MessagingResponse()
        selected_region_text = REGIONS[0]  # e.g., "Yesil District"

        # Simulate user sending the text of the selected region
        # (or "1" if the mapping from number to text is robust in handle_known_user)
        handle_known_user(self.user_profile, selected_region_text, response_twiml)

        mock_send_room_count_selection.assert_called_once_with(
            self.user_profile, response_twiml, selected_region_text
        )
