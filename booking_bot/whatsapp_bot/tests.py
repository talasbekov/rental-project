from django.test import TestCase
from django.contrib.auth import get_user_model
from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property
from booking_bot.bookings.models import Booking
from .handlers import handle_unknown_user, handle_known_user  # Assuming direct import
from datetime import date, timedelta
from unittest.mock import MagicMock  # For mocking Twilio's MessagingResponse

User = get_user_model()


class WhatsAppHandlerTests(TestCase):
    def setUp(self):
        # Create an admin user for property ownership
        self.admin_user = User.objects.create_user(
            username="propowner", password="testpassword"
        )
        UserProfile.objects.create(
            user=self.admin_user, role="admin", phone_number="+111000111"
        )

        self.property1 = Property.objects.create(
            name="Cosy Apartment",
            owner=self.admin_user,
            price_per_day=50.00,
            number_of_rooms=1,
            property_class="economy",
            address="1 Main St",
            area=30,
        )
        self.property2 = Property.objects.create(
            name="Luxury Villa",
            owner=self.admin_user,
            price_per_day=200.00,
            number_of_rooms=4,
            property_class="luxury",
            address="2 Ocean Drive",
            area=150,
        )
        self.test_user_phone = "+1234567890"

    def test_handle_unknown_user_registers_new_user(self):
        mock_response = MagicMock()  # Mock Twilio's MessagingResponse
        handle_unknown_user(self.test_user_phone, "/help", mock_response)

        self.assertTrue(
            User.objects.filter(
                username=f"user_{self.test_user_phone.replace('+', '')}"
            ).exists()
        )
        user = User.objects.get(
            username=f"user_{self.test_user_phone.replace('+', '')}"
        )
        self.assertTrue(
            UserProfile.objects.filter(
                user=user, phone_number=self.test_user_phone, role="user"
            ).exists()
        )
        mock_response.message.assert_called_once()  # Check if a message was sent
        self.assertIn("Welcome! Registered as", mock_response.message.call_args[0][0])

    def test_handle_known_user_book_command_success(self):
        # Register user first
        mock_reg_response = MagicMock()
        handle_unknown_user(self.test_user_phone, "/help", mock_reg_response)
        user_profile = UserProfile.objects.get(phone_number=self.test_user_phone)

        mock_book_response = MagicMock()
        start_date_str = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
        end_date_str = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")  # 2 days

        booking_command = f"/book property_id:{self.property1.id} from:{start_date_str} to:{end_date_str}"
        handle_known_user(user_profile, booking_command, mock_book_response)

        self.assertTrue(
            Booking.objects.filter(
                user=user_profile.user, property=self.property1
            ).exists()
        )
        booking = Booking.objects.get(user=user_profile.user, property=self.property1)
        self.assertEqual(booking.total_price, 2 * self.property1.price_per_day)
        self.assertEqual(booking.status, "pending")
        mock_book_response.message.assert_called_once()
        self.assertIn("Booking successful!", mock_book_response.message.call_args[0][0])

    def test_handle_known_user_book_command_property_not_found(self):
        mock_reg_response = MagicMock()
        handle_unknown_user(self.test_user_phone, "/help", mock_reg_response)
        user_profile = UserProfile.objects.get(phone_number=self.test_user_phone)

        mock_book_response = MagicMock()
        start_date_str = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
        end_date_str = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")

        booking_command = f"/book property_id:9999 from:{start_date_str} to:{end_date_str}"  # Non-existent ID
        handle_known_user(user_profile, booking_command, mock_book_response)

        self.assertFalse(
            Booking.objects.filter(user=user_profile.user).exists()
        )  # No booking created
        mock_book_response.message.assert_called_once()
        self.assertIn(
            "Property with ID 9999 not found.",
            mock_book_response.message.call_args[0][0],
        )

    def test_handle_known_user_book_command_unavailable(self):
        # Register user
        mock_reg_response = MagicMock()
        handle_unknown_user(self.test_user_phone, "/help", mock_reg_response)
        user_profile = UserProfile.objects.get(phone_number=self.test_user_phone)

        # Pre-existing booking
        start_date = date.today() + timedelta(days=10)
        end_date = date.today() + timedelta(days=12)
        Booking.objects.create(
            user=user_profile.user,  # Can be another user too
            property=self.property1,
            start_date=start_date,
            end_date=end_date,
            total_price=100,  # Dummy
            status="confirmed",
        )

        mock_book_response = MagicMock()
        booking_command = f"/book property_id:{self.property1.id} from:{start_date.strftime('%Y-%m-%d')} to:{end_date.strftime('%Y-%m-%d')}"
        handle_known_user(user_profile, booking_command, mock_book_response)

        mock_book_response.message.assert_called_once()
        self.assertIn(
            f"Sorry, {self.property1.name} is not available for the selected dates.",
            mock_book_response.message.call_args[0][0],
        )

    # Add more tests for other booking validations (past dates, end before start)
    # Add tests for /mybookings, /cancel_booking, /pay (mocking kaspi service)
    # Add tests for admin commands with role checks
