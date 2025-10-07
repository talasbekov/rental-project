"""
Тесты безопасности для бронирований (Claude Code Этап 31)
"""
from datetime import date, timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property, District, City
from booking_bot.bookings.models import Booking

User = get_user_model()


class BookingSecurityTestCase(TestCase):
    """Тесты валидации пересечений бронирований"""

    def setUp(self):
        # Создаём пользователя
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            telegram_chat_id='12345'
        )

        # Создаём объект недвижимости
        self.city = City.objects.create(name='Алматы')
        self.district = District.objects.create(name='Медеуский', city=self.city)
        self.property = Property.objects.create(
            name='Test Property',
            description='Test description',
            address='Test address',
            district=self.district,
            number_of_rooms=2,
            area=50.0,
            property_class='comfort',
            owner=self.user,
            price_per_day=10000
        )

    def test_booking_overlap_validation(self):
        """Тест: нельзя создать пересекающиеся бронирования"""
        # Создаём первое бронирование
        booking1 = Booking.objects.create(
            user=self.user,
            property=self.property,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=3),
            total_price=30000,
            status='confirmed'
        )

        # Пытаемся создать пересекающееся бронирование
        booking2 = Booking(
            user=self.user,
            property=self.property,
            start_date=date.today() + timedelta(days=2),
            end_date=date.today() + timedelta(days=5),
            total_price=30000,
            status='pending_payment'
        )

        # Должна возникнуть ошибка валидации
        with self.assertRaises(ValidationError) as context:
            booking2.clean()

        self.assertIn('пересекаются', str(context.exception))

    def test_booking_no_overlap_validation(self):
        """Тест: можно создать непересекающиеся бронирования"""
        # Создаём первое бронирование
        Booking.objects.create(
            user=self.user,
            property=self.property,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=3),
            total_price=30000,
            status='confirmed'
        )

        # Создаём НЕпересекающееся бронирование
        booking2 = Booking(
            user=self.user,
            property=self.property,
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=13),
            total_price=30000,
            status='pending_payment'
        )

        # Не должно быть ошибок
        try:
            booking2.clean()
        except ValidationError:
            self.fail("ValidationError raised for non-overlapping bookings")
