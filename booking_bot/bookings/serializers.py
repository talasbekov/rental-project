from rest_framework import serializers
from .models import Booking
from booking_bot.listings.models import Property # Import Property for nested serializer
from datetime import date

class PropertyMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = ['id', 'name']

class BookingSerializer(serializers.ModelSerializer):
    # Write-only fields clients POST:
    property_id = serializers.PrimaryKeyRelatedField(
        source='property',
        queryset=Property.objects.all(),
        write_only=True,
        help_text="ID of the Property to book"
    )

    # Read-only nested/detail fields:
    property_details = PropertyMiniSerializer(source='property', read_only=True)
    status_display   = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id',
            'property_id',     # clients POST this
            'property_details',# clients SEE this
            'user',
            'start_date', 'end_date',
            'total_price',
            'status', 'status_display',
            'kaspi_payment_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = (
            'user', 'total_price', 'status', 'status_display',
            'property_details', 'kaspi_payment_id',
            'created_at', 'updated_at'
        )

    def validate(self, data):
        sd = data.get('start_date')
        ed = data.get('end_date')
        if sd and ed and sd >= ed:
            raise serializers.ValidationError("End date must be after start date.")
        return data

    # create method will be handled in the view to set user and calculate price
