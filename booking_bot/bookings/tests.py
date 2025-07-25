from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from .admin import BookingAdmin
from .models import Booking, Property
from booking_bot.users.models import UserProfile # For creating property owner
from datetime import date, timedelta

class BookingAdminTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.booking_admin = BookingAdmin(Booking, self.site)
        self.factory = RequestFactory()

        # Create a user to be property owner
        self.owner_user = User.objects.create_user(username='owner', password='password')
        UserProfile.objects.create(user=self.owner_user, role='admin') # Property owner must be 'admin' role based on model limit_choices_to

        self.property = Property.objects.create(
            name="Test Property",
            owner=self.owner_user,
            price_per_day=100.00,
            number_of_rooms=2,
            property_class='economy',
            address="123 Test St",
            area=50.0
        )
        self.booking_user = User.objects.create_user(username='booker', password='password')
        UserProfile.objects.create(user=self.booking_user, role='user')


    def test_save_model_calculates_total_price(self):
        """ Test that total_price is calculated in BookingAdmin.save_model """
        start_date = date.today() + timedelta(days=1)
        end_date = date.today() + timedelta(days=3) # 2 days duration

        # Create a dummy form and booking instance (not saved yet)
        # In a real scenario, the form would come from ModelAdmin.get_form()
        # Here we simulate the object that save_model would receive.
        booking_instance = Booking(
            user=self.booking_user,
            property=self.property,
            start_date=start_date,
            end_date=end_date,
            status='pending'
            # total_price is NOT set here
        )

        # Mock the request and form (form isn't heavily used in our save_model if obj has attrs)
        request = self.factory.get('/') # Dummy request
        request.user = self.owner_user # Admin user making the change

        class DummyBookingForm: # Mock form
            def __init__(self, instance): self.instance = instance; self.errors = {}
            def add_error(self, field, error_msg): self.errors[field] = error_msg

        form = DummyBookingForm(instance=booking_instance)

        # Call save_model (this will modify booking_instance in place and then save)
        # For the test, we are interested in obj.total_price *before* super().save_model
        # but since save_model calls super().save_model() which saves it, we check after.
        self.booking_admin.save_model(request, booking_instance, form, change=False) # change=False for new object

        # booking_instance should now be saved by super().save_model()
        # and total_price should be calculated.
        saved_booking = Booking.objects.get(id=booking_instance.id)

        expected_price = 2 * self.property.price_per_day # 2 days * 100.00
        self.assertEqual(saved_booking.total_price, expected_price)
