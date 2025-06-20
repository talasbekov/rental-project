from rest_framework import serializers
from .models import Booking
from booking_bot.listings.models import Property # Import Property for nested serializer
from datetime import date

# Simple serializer for nested property details
class PropertyMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = ['id', 'name']

class BookingSerializer(serializers.ModelSerializer):
    # бот будет слать сюда telegram_id
    telegram_id = serializers.IntegerField(write_only=True)
    property_details = PropertyMiniSerializer(source='property', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'property', 'property_details', 'user', 'start_date',
            'end_date', 'total_price', 'status', 'status_display',
            'kaspi_payment_id', 'created_at', 'updated_at', 'telegram_id'
        ]
        read_only_fields = (
            'user', 'total_price', 'status', 'status_display',
            'property_details', 'kaspi_payment_id', 'created_at', 'updated_at'
        )

    def validate(self, data):
        """
        Check that start_date is before end_date.
        Check that property is available (basic check, can be more complex).
        """
        if 'start_date' in data and 'end_date' in data:
            if data['start_date'] >= data['end_date']:
                raise serializers.ValidationError("End date must be after start date.")

        # More complex availability checks might query existing bookings for the property
        # For now, this is a basic validation.
        return data

    # create method will be handled in the view to set user and calculate price
