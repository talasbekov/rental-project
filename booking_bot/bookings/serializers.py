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
    property_details = PropertyMiniSerializer(source='property', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    # Add telegram_chat_id for write operations, not part of the model instance representation
    telegram_chat_id = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'property', 'property_details', 'user', 'start_date',
            'end_date', 'total_price', 'status', 'status_display',
            'kaspi_payment_id', 'created_at', 'updated_at',
            'telegram_chat_id' # Add to fields list
        ]
        read_only_fields = (
            'user', 'total_price', 'status', 'status_display',
            'property_details', 'kaspi_payment_id', 'created_at', 'updated_at'
        )

    def validate(self, data):
        """
        Check that start_date is before end_date.
        """
        if 'start_date' in data and 'end_date' in data:
            if data['start_date'] >= data['end_date']:
                raise serializers.ValidationError("End date must be after start date.")
        return data
