from rest_framework import serializers
from .models import Booking
from datetime import date

class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ('total_price', 'status', 'user') # User will be set from request, status initial

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
