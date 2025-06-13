from django.db import models
from django.contrib.auth.models import User
from booking_bot.listings.models import Property

class Booking(models.Model):
    BOOKING_STATUS_CHOICES = [
        ('pending', 'Pending'), # Default state after creation by user, before payment attempt
        ('pending_payment', 'Pending Payment'), # After user selected property, before Kaspi payment link generation
        ('payment_failed', 'Payment Failed'), # If Kaspi payment initiation fails
        ('confirmed', 'Confirmed'), # After successful payment via Kaspi
        ('cancelled', 'Cancelled'), # If user or admin cancels
        ('completed', 'Completed'), # After the booking period has passed successfully
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='bookings')
    start_date = models.DateField()
    end_date = models.DateField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=BOOKING_STATUS_CHOICES, default='pending')
    kaspi_payment_id = models.CharField(max_length=255, null=True, blank=True, unique=True, help_text="Kaspi's unique ID for the payment attempt")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Booking for {self.property.name} by {self.user.username}"

    # Potentially add a clean method to validate dates (end_date > start_date)
    # and calculate total_price based on property.price_per_day and duration
