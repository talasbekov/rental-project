"""Property API views."""

from __future__ import annotations

from datetime import date, timedelta

from django.db import models  # type: ignore
from django.shortcuts import get_object_or_404  # type: ignore
from rest_framework import permissions, serializers, status, viewsets, generics  # type: ignore
from rest_framework.filters import OrderingFilter  # type: ignore
from django_filters.rest_framework import DjangoFilterBackend  # type: ignore
from rest_framework.decorators import action  # type: ignore
from rest_framework.response import Response  # type: ignore
from rest_framework.views import APIView  # type: ignore

from .models import (
    Amenity,
    Property,
    PropertyAccessInfo,
    PropertyAccessLog,
    PropertyAvailability,
    PropertyCalendarSettings,
    PropertySeasonalRate,
    PropertyType,
)
from .serializers import (
    AmenitySerializer,
    PropertyAccessInfoSerializer,
    PropertyAccessLogSerializer,
    PropertyAvailabilitySerializer,
    PropertyAvailabilityWriteSerializer,
    PropertyCalendarSettingsSerializer,
    PropertyPublicCalendarSerializer,
    PropertySeasonalRateSerializer,
    PropertySeasonalRateWriteSerializer,
    PropertySerializer,
    PropertyTypeSerializer,
    PropertyWriteSerializer,
)
from .filters import PropertyFilterSet


class IsPropertyOwnerOrAdmin(permissions.BasePermission):
    """Позволяет управлять объектом его владельцу, супер админам и персоналу."""

    def has_permission(self, request, view):  # type: ignore
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not user.is_authenticated:
            return False
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return True
        action = getattr(view, "action", None)
        if action == "create":
            return hasattr(user, "is_realtor") and user.is_realtor() or (
                hasattr(user, "is_super_admin") and user.is_super_admin()
            )
        return True

    def has_object_permission(self, request, view, obj: Property):  # type: ignore
        user = request.user
        if not user.is_authenticated:
            return False
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return True
        if hasattr(user, "is_super_admin") and user.is_super_admin():
            # Супер-админ может управлять объектами агентства
            return obj.agency_id == getattr(user.agency, "id", None)
        if hasattr(user, "is_realtor") and user.is_realtor():
            return obj.owner_id == user.id
        return False


class PropertyViewSet(viewsets.ModelViewSet):
    """Viewset для управления объектами недвижимости."""

    queryset = Property.objects.select_related("owner", "agency", "property_type").prefetch_related(
        "amenities", "photos", "seasonal_rates", "availability_periods"
    )
    permission_classes = [IsPropertyOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = PropertyFilterSet
    ordering_fields = [
        "base_price",
        "created_at",
        "is_featured",
        "rooms",
    ]

    def get_permissions(self):  # type: ignore
        if self.action in {"list", "retrieve"}:
            return [permissions.AllowAny()]
        return super().get_permissions()

    def get_queryset(self):  # type: ignore
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.filter(status=Property.Status.ACTIVE)
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return qs
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return qs
        if hasattr(user, "is_super_admin") and user.is_super_admin():
            return qs.filter(agency=user.agency)
        if hasattr(user, "is_realtor") and user.is_realtor():
            return qs.filter(owner=user)
        return qs.filter(status=Property.Status.ACTIVE)

    def get_serializer_class(self):  # type: ignore
        if self.action in {"create", "update", "partial_update"}:
            return PropertyWriteSerializer
        return PropertySerializer

    def perform_create(self, serializer):  # type: ignore
        serializer.save()

    @action(detail=True, methods=["get"], url_path="access-info")
    def get_access_info(self, request, pk=None):  # type: ignore
        """
        Retrieve encrypted access codes for a property.

        Only accessible by:
        - Property owner (realtor)
        - Agency super admin
        - Platform superusers/staff
        - Guest with active booking for this property

        All access is logged for security audit.
        """
        property_obj = self.get_object()
        user = request.user

        # Authorization check
        can_access = False
        reason = ""

        # Property owner
        if property_obj.owner_id == user.id:
            can_access = True
            reason = "Property owner access"

        # Agency super admin
        elif (
            hasattr(user, "is_super_admin")
            and user.is_super_admin()
            and property_obj.agency_id == getattr(user.agency, "id", None)
        ):
            can_access = True
            reason = "Agency super admin access"

        # Platform staff
        elif getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            can_access = True
            reason = "Platform staff access"

        # Platform superuser
        elif hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            can_access = True
            reason = "Platform superuser access"

        # Guest with active booking
        else:
            from apps.bookings.models import Booking
            from django.utils import timezone

            active_booking = Booking.objects.filter(
                property=property_obj,
                guest=user,
                status__in=[
                    Booking.Status.CONFIRMED,
                    Booking.Status.IN_PROGRESS,
                ],
                check_in__lte=timezone.now().date(),
                check_out__gte=timezone.now().date(),
            ).first()

            if active_booking:
                can_access = True
                reason = f"Active booking #{active_booking.id}"

        if not can_access:
            return Response(
                {"detail": "У вас нет прав для доступа к информации об этом объекте."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Get or create access info
        access_info, created = PropertyAccessInfo.objects.get_or_create(
            property=property_obj
        )

        # Log access to each non-empty field
        ip_address = self._get_client_ip(request)
        for field_name in ["door_code", "apartment_code", "safe_code"]:
            field_value = getattr(access_info, field_name, "")
            if field_value:  # Only log if field has a value
                PropertyAccessLog.objects.create(
                    access_info=access_info,
                    accessed_by=user,
                    field_name=field_name,
                    reason=reason,
                    ip_address=ip_address,
                )

        serializer = PropertyAccessInfoSerializer(access_info)
        return Response(serializer.data)

    @staticmethod
    def _get_client_ip(request):  # type: ignore
        """Extract client IP from request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class SearchPropertiesView(generics.ListAPIView):
    """Search endpoint with filters, ordering and optional availability window."""

    serializer_class = PropertySerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = PropertyFilterSet
    ordering_fields = [
        "base_price",
        "created_at",
        "is_featured",
        "rooms",
    ]

    def get_queryset(self):  # type: ignore
        qs = Property.objects.select_related("owner", "agency", "property_type").prefetch_related(
            "amenities", "photos",
        ).filter(status=Property.Status.ACTIVE)

        # Optional availability filter by start/end
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")

        if start and end:
            # Exclude properties with blocking availability periods
            blocking_statuses = [
                PropertyAvailability.AvailabilityStatus.BOOKED,
                PropertyAvailability.AvailabilityStatus.BLOCKED,
                PropertyAvailability.AvailabilityStatus.MAINTENANCE,
            ]
            blocked_ids = PropertyAvailability.objects.filter(
                start_date__lt=end,
                end_date__gt=start,
                status__in=blocking_statuses,
            ).values_list("property_id", flat=True)

            # Exclude properties with overlapping active bookings
            from apps.bookings.models import Booking

            overlapping_bookings = Booking.objects.filter(
                check_in__lt=end,
                check_out__gt=start,
                status__in=[
                    Booking.Status.PENDING,
                    Booking.Status.CONFIRMED,
                    Booking.Status.IN_PROGRESS,
                ],
            ).values_list("property_id", flat=True)

            qs = qs.exclude(id__in=blocked_ids).exclude(id__in=overlapping_bookings)

        return qs


class PropertyTypeViewSet(viewsets.ModelViewSet):
    """CRUD для типов недвижимости (только для персонала)."""

    queryset = PropertyType.objects.all()
    serializer_class = PropertyTypeSerializer
    permission_classes = [permissions.IsAdminUser]


class AmenityViewSet(viewsets.ModelViewSet):
    """CRUD для удобств (только для персонала)."""

    queryset = Amenity.objects.all()
    serializer_class = AmenitySerializer
    permission_classes = [permissions.IsAdminUser]


class PropertyCalendarMixin:
    """Вспомогательный миксин для получения объекта и проверки прав."""

    property_lookup_url_kwarg = "property_id"
    permission_classes = [permissions.IsAuthenticated, IsPropertyOwnerOrAdmin]

    def initial(self, request, *args, **kwargs):  # type: ignore
        super().initial(request, *args, **kwargs)
        property_id = kwargs.get(self.property_lookup_url_kwarg)
        self.property_object = get_object_or_404(Property, pk=property_id)
        self.check_object_permissions(request, self.property_object)

    def get_property(self) -> Property:
        return self.property_object

    def get_serializer_context(self):  # type: ignore
        context = super().get_serializer_context()
        context["property"] = getattr(self, "property_object", None)
        return context


class PropertyAvailabilityViewSet(
    PropertyCalendarMixin,
    viewsets.ModelViewSet,
):
    """Управление блокировками и событиями доступности календаря."""

    serializer_class = PropertyAvailabilitySerializer
    queryset = PropertyAvailability.objects.select_related("property", "created_by").all()

    def get_serializer_class(self):  # type: ignore
        if self.action in {"create", "update", "partial_update"}:
            return PropertyAvailabilityWriteSerializer
        return PropertyAvailabilitySerializer

    def get_queryset(self):  # type: ignore
        qs = super().get_queryset().filter(property=self.get_property())
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        availability_type = self.request.query_params.get("availability_type")
        status_param = self.request.query_params.get("status")

        if start:
            qs = qs.filter(end_date__gte=start)
        if end:
            qs = qs.filter(start_date__lte=end)
        if availability_type:
            qs = qs.filter(availability_type=availability_type)
        if status_param:
            qs = qs.filter(status=status_param)

        return qs.order_by("start_date")

    def _validate_overlap(self, start_date: date, end_date: date, exclude_id: int | None = None) -> None:
        property_obj = self.get_property()
        overlap_filter = models.Q(start_date__lt=end_date) & models.Q(end_date__gt=start_date)
        blocking_statuses = [
            PropertyAvailability.AvailabilityStatus.BOOKED,
            PropertyAvailability.AvailabilityStatus.BLOCKED,
            PropertyAvailability.AvailabilityStatus.MAINTENANCE,
        ]
        qs = PropertyAvailability.objects.filter(
            property=property_obj,
            status__in=blocking_statuses,
        ).filter(overlap_filter)
        if exclude_id is not None:
            qs = qs.exclude(id=exclude_id)
        if qs.exists():
            raise serializers.ValidationError(
                "Невозможно создать блокировку: выбранные даты пересекаются с существующими событиями."
            )

    def perform_create(self, serializer):  # type: ignore
        start_date = serializer.validated_data["start_date"]
        end_date = serializer.validated_data["end_date"]
        self._validate_overlap(start_date, end_date)
        serializer.save(
            property=self.get_property(),
            created_by=self.request.user,
            source=serializer.validated_data.get("availability_type", PropertyAvailability.AvailabilityType.MANUAL_BLOCK),
        )

    def perform_update(self, serializer):  # type: ignore
        instance: PropertyAvailability = self.get_object()
        start_date = serializer.validated_data.get("start_date", instance.start_date)
        end_date = serializer.validated_data.get("end_date", instance.end_date)
        self._validate_overlap(start_date, end_date, exclude_id=instance.id)
        serializer.save()

    def destroy(self, request, *args, **kwargs):  # type: ignore
        instance: PropertyAvailability = self.get_object()
        if instance.availability_type in (
            PropertyAvailability.AvailabilityType.SYSTEM_BOOKING,
            PropertyAvailability.AvailabilityType.SEASONAL_OVERRIDE,
        ):
            return Response(
                {"detail": "Нельзя удалять системные блокировки."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request, property_id=None):  # type: ignore
        ids = request.data.get("ids", [])
        if not isinstance(ids, list):
            return Response({"detail": "Ожидается список идентификаторов."}, status=status.HTTP_400_BAD_REQUEST)
        deleted, _ = PropertyAvailability.objects.filter(
            property=self.get_property(),
            id__in=ids,
            availability_type__in=[
                PropertyAvailability.AvailabilityType.MANUAL_BLOCK,
                PropertyAvailability.AvailabilityType.MAINTENANCE,
            ],
        ).delete()
        return Response({"deleted": deleted}, status=status.HTTP_200_OK)
 
    def create(self, request, *args, **kwargs):  # type: ignore
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        read_serializer = PropertyAvailabilitySerializer(
            serializer.instance,
            context=self.get_serializer_context(),
        )
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):  # type: ignore
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        read_serializer = PropertyAvailabilitySerializer(
            serializer.instance,
            context=self.get_serializer_context(),
        )
        return Response(read_serializer.data, status=status.HTTP_200_OK)


class PropertySeasonalRateViewSet(
    PropertyCalendarMixin,
    viewsets.ModelViewSet,
):
    """Управление сезонными тарифами объекта."""

    serializer_class = PropertySeasonalRateSerializer
    queryset = PropertySeasonalRate.objects.select_related("property", "created_by").all()

    def get_serializer_class(self):  # type: ignore
        if self.action in {"create", "update", "partial_update"}:
            return PropertySeasonalRateWriteSerializer
        return PropertySeasonalRateSerializer

    def get_queryset(self):  # type: ignore
        qs = super().get_queryset().filter(property=self.get_property())
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if start:
            qs = qs.filter(end_date__gte=start)
        if end:
            qs = qs.filter(start_date__lte=end)
        return qs.order_by("start_date", "-priority")

    def perform_create(self, serializer):  # type: ignore
        serializer.save(
            property=self.get_property(),
            created_by=self.request.user,
        )

    def perform_update(self, serializer):  # type: ignore
        serializer.save()

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request, property_id=None):  # type: ignore
        ids = request.data.get("ids", [])
        if not isinstance(ids, list):
            return Response({"detail": "Ожидается список идентификаторов."}, status=status.HTTP_400_BAD_REQUEST)
        deleted, _ = PropertySeasonalRate.objects.filter(
            property=self.get_property(),
            id__in=ids,
        ).delete()
        return Response({"deleted": deleted}, status=status.HTTP_200_OK)
 
    def create(self, request, *args, **kwargs):  # type: ignore
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        read_serializer = PropertySeasonalRateSerializer(
            serializer.instance,
            context=self.get_serializer_context(),
        )
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):  # type: ignore
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        read_serializer = PropertySeasonalRateSerializer(
            serializer.instance,
            context=self.get_serializer_context(),
        )
        return Response(read_serializer.data, status=status.HTTP_200_OK)


class PropertyCalendarSettingsView(PropertyCalendarMixin, APIView):
    """Просмотр и изменение настроек календаря объекта."""

    def get(self, request, property_id):  # type: ignore
        property_obj = self.get_property()
        settings, _ = PropertyCalendarSettings.objects.get_or_create(property=property_obj)
        serializer = PropertyCalendarSettingsSerializer(settings)
        return Response(serializer.data)

    def put(self, request, property_id):  # type: ignore
        return self._update(request, property_id, partial=False)

    def patch(self, request, property_id):  # type: ignore
        return self._update(request, property_id, partial=True)

    def _update(self, request, property_id, partial: bool):  # type: ignore
        property_obj = self.get_property()
        settings, _ = PropertyCalendarSettings.objects.get_or_create(property=property_obj)
        serializer = PropertyCalendarSettingsSerializer(
            settings,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PropertyPublicCalendarView(APIView):
    """Возвращает агрегированную информацию календаря для публичного отображения."""

    def get(self, request, property_id):  # type: ignore
        property_obj = get_object_or_404(Property, pk=property_id, status=Property.Status.ACTIVE)
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        if not start or not end:
            return Response(
                {"detail": "Параметры start и end обязательны."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        availability_qs = PropertyAvailability.objects.filter(
            property=property_obj,
            start_date__lte=end,
            end_date__gte=start,
        )
        seasonal_qs = PropertySeasonalRate.objects.filter(
            property=property_obj,
            start_date__lte=end,
            end_date__gte=start,
        )

        current = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        result = []

        while current <= end_date:
            status_value = PropertyAvailability.AvailabilityStatus.AVAILABLE
            min_nights = property_obj.min_nights
            final_price = property_obj.base_price
            pricing_source = "base"

            for availability in availability_qs:
                if availability.start_date <= current <= availability.end_date:
                    status_value = availability.status
                    break

            for seasonal in seasonal_qs:
                if seasonal.start_date <= current <= seasonal.end_date:
                    final_price = seasonal.price_per_night
                    pricing_source = "seasonal"
                    if seasonal.min_nights:
                        min_nights = max(min_nights, seasonal.min_nights)
                    if seasonal.max_nights:
                        min_nights = min(min_nights, seasonal.max_nights)
                    break

            result.append(
                {
                    "date": current,
                    "status": status_value,
                    "final_price": final_price,
                    "pricing_source": pricing_source,
                    "min_nights": min_nights,
                }
            )
            current = current + timedelta(days=1)

        serializer = PropertyPublicCalendarSerializer(result, many=True)
        return Response({"property_id": property_obj.id, "dates": serializer.data})
