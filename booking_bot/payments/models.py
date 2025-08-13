from django.db import models
from booking_bot.bookings.models import Booking


class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("successful", "Successful"),
        ("failed", "Failed"),
    ]
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="payments"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=50, blank=True, null=True
    )  # e.g., 'kaspi.kz', 'stripe_card'
    transaction_id = models.CharField(
        max_length=100, blank=True, null=True
    )  # From payment gateway
    status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment for Booking ID {self.booking.id} - {self.status}"
