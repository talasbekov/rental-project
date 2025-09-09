from rest_framework import serializers
from .models import Property, Review, ReviewPhoto, District, City
from booking_bot.bookings.models import Booking
from django.contrib.auth.models import User


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['id', 'name']


class DistrictSerializer(serializers.ModelSerializer):
    city = CitySerializer(read_only=True)
    city_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = District
        fields = ['id', 'name', 'city', 'city_id']


class ReviewPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewPhoto
        fields = ['id', 'image_url', 'caption']


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    photos = ReviewPhotoSerializer(many=True, read_only=True)
    
    class Meta:
        model = Review
        fields = ['id', 'user_name', 'rating', 'comment', 'photos', 'created_at', 'is_approved']


class PropertySerializer(serializers.ModelSerializer):
    district = DistrictSerializer(read_only=True)
    district_id = serializers.IntegerField(write_only=True, required=False)
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    rating_display = serializers.CharField(source='rating_stars', read_only=True)
    
    class Meta:
        model = Property
        fields = [
            'id', 'name', 'description', 'address', 'district', 'district_id',
            'number_of_rooms', 'area', 'property_class', 'status', 'entry_floor',
            'entry_instructions', 'owner', 'owner_username', 'price_per_day',
            'average_rating', 'reviews_count', 'rating_display', 'reviews',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'average_rating', 'reviews_count']
        

class PropertyAdminSerializer(PropertySerializer):
    """Extended serializer for admin users with access codes"""
    entry_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    key_safe_code = serializers.CharField(write_only=True, required=False, allow_blank=True)  
    digital_lock_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    # Read-only fields for displaying codes (will be handled in view based on permissions)
    entry_code_display = serializers.SerializerMethodField()
    key_safe_code_display = serializers.SerializerMethodField()
    digital_lock_code_display = serializers.SerializerMethodField()
    
    def get_entry_code_display(self, obj):
        # Only return if user is owner or admin (checked in view)
        return getattr(obj, '_display_entry_code', None)
    
    def get_key_safe_code_display(self, obj):
        return getattr(obj, '_display_key_safe_code', None)
        
    def get_digital_lock_code_display(self, obj):
        return getattr(obj, '_display_digital_lock_code', None)
    
    def update(self, instance, validated_data):
        # Handle encrypted fields
        if 'entry_code' in validated_data:
            instance.entry_code = validated_data.pop('entry_code')
        if 'key_safe_code' in validated_data:
            instance.key_safe_code = validated_data.pop('key_safe_code')
        if 'digital_lock_code' in validated_data:
            instance.digital_lock_code = validated_data.pop('digital_lock_code')
            
        return super().update(instance, validated_data)
    
    def create(self, validated_data):
        # Handle encrypted fields during creation
        entry_code = validated_data.pop('entry_code', '')
        key_safe_code = validated_data.pop('key_safe_code', '')
        digital_lock_code = validated_data.pop('digital_lock_code', '')
        
        instance = super().create(validated_data)
        
        if entry_code:
            instance.entry_code = entry_code
        if key_safe_code:
            instance.key_safe_code = key_safe_code
        if digital_lock_code:
            instance.digital_lock_code = digital_lock_code
            
        instance.save()
        return instance
    
    class Meta(PropertySerializer.Meta):
        fields = PropertySerializer.Meta.fields + [
            'entry_code', 'key_safe_code', 'digital_lock_code',
            'entry_code_display', 'key_safe_code_display', 'digital_lock_code_display'
        ]


class PropertyBookingSerializer(serializers.ModelSerializer):
    """Serializer for booking information"""
    guest_name = serializers.CharField(source='user.username', read_only=True)
    property_name = serializers.CharField(source='property.name', read_only=True)
    
    class Meta:
        model = Booking
        fields = [
            'id', 'guest_name', 'property_name', 'start_date', 'end_date', 
            'status', 'total_price', 'created_at'
        ]
