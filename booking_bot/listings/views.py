from datetime import date

from rest_framework import viewsets, filters as drf_filters, permissions
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Avg
from django.db import models
from .models import Property, PropertyCalendarManager, Review
from .serializers import (
    PropertySerializer, PropertyAdminSerializer, PropertyBookingSerializer, ReviewSerializer
)
from .filters import PropertyFilter  # Import the custom filter
from rest_framework.permissions import IsAuthenticatedOrReadOnly  # Allow public read
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from booking_bot.bookings.models import Booking
from booking_bot.core.models import AuditLog
import logging

logger = logging.getLogger(__name__)


class PropertyViewSet(viewsets.ModelViewSet):
    queryset = Property.objects.all()
    serializer_class = PropertySerializer
    permission_classes = [
        IsAuthenticatedOrReadOnly
    ]  # Allow anyone to view, but only auth users to change
    filter_backends = [
        DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter,
    ]
    filterset_class = PropertyFilter
    search_fields = ["name", "address", "description"]
    ordering_fields = ["price_per_day", "created_at", "area", "number_of_rooms"]
    ordering = ["-created_at"]

    @action(detail=True, methods=["get"])
    def calendar(self, request, pk=None):
        """Получение календаря занятости квартиры"""
        property_obj = self.get_object()

        year = int(request.query_params.get("year", date.today().year))
        month = int(request.query_params.get("month", date.today().month))

        calendar_matrix = PropertyCalendarManager.get_calendar_view(
            property_obj, year, month
        )

        occupancy_rate = PropertyCalendarManager.get_occupancy_rate(
            property_obj,
            date(year, month, 1),
            date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1),
        )

        return Response(
            {
                "property": property_obj.id,
                "year": year,
                "month": month,
                "calendar": calendar_matrix,
                "occupancy_rate": round(occupancy_rate, 2),
            }
        )

    @action(detail=True, methods=["post"])
    def block_dates(self, request, pk=None):
        """Блокировка дат владельцем"""
        property_obj = self.get_object()

        # Проверка прав (только владелец или админ)
        if property_obj.owner != request.user and not request.user.is_staff:
            return Response(
                {"error": "Недостаточно прав"}, status=status.HTTP_403_FORBIDDEN
            )

        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        reason = request.data.get("reason", "Заблокировано владельцем")

        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)

            if end <= start:
                raise ValueError("Дата окончания должна быть после даты начала")

            blocked_days = PropertyCalendarManager.block_dates(
                property_obj, start, end, status="blocked"
            )

            # Сохраняем причину блокировки
            for day in blocked_days:
                day.notes = reason
                day.save()

            return Response(
                {
                    "message": f"Заблокировано {len(blocked_days)} дней",
                    "blocked_dates": [day.date.isoformat() for day in blocked_days],
                }
            )

        except (ValueError, TypeError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def get_serializer_class(self):
        """Use admin serializer for admin users"""
        if self.request.user.is_authenticated:
            profile = getattr(self.request.user, 'profile', None)
            if profile and profile.role in ('admin', 'super_admin', 'super_user'):
                return PropertyAdminSerializer
        return PropertySerializer

    def get_queryset(self):
        """Filter properties for admin users to show only their own"""
        queryset = Property.objects.all()
        
        if self.request.user.is_authenticated:
            profile = getattr(self.request.user, 'profile', None)
            if profile and profile.role == 'admin':
                # Regular admins see only their own properties
                queryset = queryset.filter(owner=self.request.user)
            elif profile and profile.role in ('super_admin', 'super_user'):
                # Super admins see all properties
                pass
            else:
                # Regular users see all properties (read-only)
                pass
                
        return queryset

    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to add access codes for authorized users"""
        instance = self.get_object()
        
        # Check if user can view access codes
        can_view_codes = False
        if request.user.is_authenticated:
            profile = getattr(request.user, 'profile', None)
            if profile and (
                profile.role in ('admin', 'super_admin', 'super_user') and 
                (instance.owner == request.user or profile.role in ('super_admin', 'super_user'))
            ):
                can_view_codes = True
                # Log access to codes
                AuditLog.objects.create(
                    user=request.user,
                    action='view_property_codes',
                    resource_type='Property',
                    resource_id=instance.id,
                    details={'property_name': instance.name}
                )
        
        if can_view_codes:
            # Set display codes for serializer
            instance._display_entry_code = instance.entry_code
            instance._display_key_safe_code = instance.key_safe_code  
            instance._display_digital_lock_code = instance.digital_lock_code
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def my_properties(self, request):
        """Get properties owned by current user"""
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in ('admin', 'super_admin', 'super_user'):
            return Response(
                {"error": "Недостаточно прав"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        properties = Property.objects.filter(owner=request.user)
        serializer = self.get_serializer(properties, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def bookings(self, request, pk=None):
        """Get bookings for a property"""
        property_obj = self.get_object()
        
        # Check permissions
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in ('admin', 'super_admin', 'super_user'):
            return Response(
                {"error": "Недостаточно прав"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if property_obj.owner != request.user and profile.role != 'super_admin':
            return Response(
                {"error": "Недостаточно прав"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        bookings = Booking.objects.filter(property=property_obj).order_by('-created_at')
        
        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            bookings = bookings.filter(status=status_filter)
        
        serializer = PropertyBookingSerializer(bookings, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def reviews(self, request, pk=None):
        """Get reviews for a property"""
        property_obj = self.get_object()
        
        # Check permissions
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in ('admin', 'super_admin', 'super_user'):
            return Response(
                {"error": "Недостаточно прав"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if property_obj.owner != request.user and profile.role != 'super_admin':
            return Response(
                {"error": "Недостаточно прав"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        reviews = Review.objects.filter(property=property_obj).order_by('-created_at')
        serializer = ReviewSerializer(reviews, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def dashboard(self, request):
        """Admin dashboard with statistics"""
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role not in ('admin', 'super_admin', 'super_user'):
            return Response(
                {"error": "Недостаточно прав"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if profile.role in ('super_admin', 'super_user'):
            properties = Property.objects.all()
        else:
            properties = Property.objects.filter(owner=request.user)
        
        # Get statistics
        total_properties = properties.count()
        active_bookings = Booking.objects.filter(
            property__in=properties,
            status__in=['confirmed', 'pending_payment']
        ).count()
        
        completed_bookings = Booking.objects.filter(
            property__in=properties,
            status='completed'
        ).count()
        
        total_reviews = Review.objects.filter(property__in=properties).count()
        avg_rating = properties.aggregate(
            avg_rating=models.Avg('average_rating')
        )['avg_rating'] or 0
        
        return Response({
            'total_properties': total_properties,
            'active_bookings': active_bookings,
            'completed_bookings': completed_bookings,
            'total_reviews': total_reviews,
            'average_rating': round(avg_rating, 2)
        })
