"""Serializers for Super Admin API."""

from __future__ import annotations

from rest_framework import serializers  # type: ignore

from apps.users.models import CustomUser, RealEstateAgency


class RealtorListSerializer(serializers.ModelSerializer):
    """Serializer for listing realtors in the agency."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    is_active = serializers.BooleanField(source="is_active", read_only=True)
    properties_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "username",
            "phone",
            "role",
            "role_display",
            "agency_id",
            "avatar",
            "is_active",
            "is_email_verified",
            "is_phone_verified",
            "last_activity_at",
            "created_at",
            "properties_count",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "last_activity_at",
        ]

    def get_properties_count(self, obj: CustomUser) -> int:
        """Count active properties for this realtor."""
        return obj.properties.filter(status="active").count()


class RealtorDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for a single realtor."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    agency_name = serializers.CharField(source="agency.name", read_only=True)
    properties_count = serializers.SerializerMethodField()
    bookings_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "username",
            "phone",
            "role",
            "role_display",
            "agency_id",
            "agency_name",
            "avatar",
            "telegram_id",
            "is_active",
            "is_email_verified",
            "is_phone_verified",
            "is_identity_verified",
            "last_activity_at",
            "created_at",
            "updated_at",
            "properties_count",
            "bookings_count",
        ]
        read_only_fields = [
            "id",
            "role_display",
            "agency_name",
            "created_at",
            "updated_at",
            "last_activity_at",
            "properties_count",
            "bookings_count",
        ]

    def get_properties_count(self, obj: CustomUser) -> int:
        """Count all properties for this realtor."""
        return obj.properties.count()

    def get_bookings_count(self, obj: CustomUser) -> int:
        """Count all bookings for this realtor's properties."""
        from apps.bookings.models import Booking
        return Booking.objects.filter(property__owner=obj).count()


class RealtorCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new realtor in the agency."""

    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        min_length=8,
    )

    class Meta:
        model = CustomUser
        fields = [
            "email",
            "username",
            "phone",
            "password",
            "telegram_id",
        ]

    def validate_email(self, value: str) -> str:
        """Check email is unique."""
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует.")
        return value

    def validate_phone(self, value: str) -> str:
        """Check phone is unique."""
        if CustomUser.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Пользователь с таким телефоном уже существует.")
        return value

    def create(self, validated_data: dict) -> CustomUser:  # type: ignore
        """Create realtor with hashed password and correct role."""
        password = validated_data.pop("password")

        # Get agency from context (set by view)
        agency = self.context.get("agency")

        # Create realtor user
        user = CustomUser.objects.create_user(
            email=validated_data["email"],
            password=password,
            username=validated_data.get("username", ""),
            phone=validated_data["phone"],
            role=CustomUser.RoleChoices.REALTOR,
            agency=agency,
            telegram_id=validated_data.get("telegram_id"),
        )

        return user


class RealtorUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating realtor details."""

    class Meta:
        model = CustomUser
        fields = [
            "username",
            "phone",
            "telegram_id",
            "is_active",
            "is_email_verified",
            "is_phone_verified",
            "is_identity_verified",
        ]

    def validate_phone(self, value: str) -> str:
        """Check phone is unique (excluding current user)."""
        user = self.instance
        if CustomUser.objects.filter(phone=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("Пользователь с таким телефоном уже существует.")
        return value


class RealtorStatsSerializer(serializers.Serializer):
    """Serializer for realtor performance statistics."""

    realtor_id = serializers.IntegerField()
    realtor_name = serializers.CharField()
    realtor_email = serializers.EmailField()

    properties_count = serializers.IntegerField()
    active_properties = serializers.IntegerField()

    total_bookings = serializers.IntegerField()
    confirmed_bookings = serializers.IntegerField()
    completed_bookings = serializers.IntegerField()
    cancelled_bookings = serializers.IntegerField()

    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_booking_value = serializers.DecimalField(max_digits=10, decimal_places=2)

    # Optional period filters
    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)


class AgencyStatsSerializer(serializers.Serializer):
    """Serializer for agency-level statistics."""

    agency_id = serializers.IntegerField()
    agency_name = serializers.CharField()

    total_realtors = serializers.IntegerField()
    active_realtors = serializers.IntegerField()

    total_properties = serializers.IntegerField()
    active_properties = serializers.IntegerField()

    total_bookings = serializers.IntegerField()
    confirmed_bookings = serializers.IntegerField()
    completed_bookings = serializers.IntegerField()

    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_booking_value = serializers.DecimalField(max_digits=10, decimal_places=2)

    # Top performers
    top_realtors = RealtorStatsSerializer(many=True, required=False)
    top_properties = serializers.ListField(required=False)


class AgencySerializer(serializers.ModelSerializer):
    """Serializer for RealEstateAgency model."""

    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    realtors_count = serializers.SerializerMethodField()
    properties_count = serializers.SerializerMethodField()

    class Meta:
        model = RealEstateAgency
        fields = [
            "id",
            "name",
            "description",
            "city",
            "address",
            "phone",
            "email",
            "website",
            "telegram_chat_id",
            "commission_rate",
            "properties_limit",
            "realtors_limit",
            "owner_id",
            "owner_email",
            "is_active",
            "created_at",
            "updated_at",
            "realtors_count",
            "properties_count",
        ]
        read_only_fields = [
            "id",
            "owner_id",
            "owner_email",
            "created_at",
            "updated_at",
            "realtors_count",
            "properties_count",
        ]

    def get_realtors_count(self, obj: RealEstateAgency) -> int:
        """Count active realtors in agency."""
        return obj.employees.filter(role=CustomUser.RoleChoices.REALTOR, is_active=True).count()

    def get_properties_count(self, obj: RealEstateAgency) -> int:
        """Count active properties in agency."""
        return obj.properties.filter(status="active").count()