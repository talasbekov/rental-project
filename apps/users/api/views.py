"""API views for Super Admin operations."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import models  # type: ignore
from django.utils import timezone  # type: ignore
from rest_framework import viewsets, status, permissions  # type: ignore
from rest_framework.decorators import action  # type: ignore
from rest_framework.response import Response  # type: ignore

from apps.users.models import CustomUser, RealEstateAgency
from .permissions import IsSuperAdmin, IsAgencyOwner
from .serializers import (
    RealtorListSerializer,
    RealtorDetailSerializer,
    RealtorCreateSerializer,
    RealtorUpdateSerializer,
    RealtorStatsSerializer,
    AgencyStatsSerializer,
    AgencySerializer,
)


class RealtorViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Super Admin to manage realtors in their agency.

    Endpoints:
    - GET /api/v1/super-admin/realtors/ - list all realtors in agency
    - POST /api/v1/super-admin/realtors/ - create new realtor
    - GET /api/v1/super-admin/realtors/{id}/ - get realtor details
    - PATCH /api/v1/super-admin/realtors/{id}/ - update realtor
    - DELETE /api/v1/super-admin/realtors/{id}/ - delete realtor
    - POST /api/v1/super-admin/realtors/{id}/deactivate/ - deactivate realtor
    - POST /api/v1/super-admin/realtors/{id}/activate/ - activate realtor
    - GET /api/v1/super-admin/realtors/{id}/stats/ - realtor performance stats
    """

    queryset = CustomUser.objects.select_related("agency").all()
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get_serializer_class(self) -> type:  # type: ignore
        """Return serializer class based on action."""
        if self.action == "list":
            return RealtorListSerializer  # type: ignore
        if self.action == "create":
            return RealtorCreateSerializer  # type: ignore
        if self.action in ["update", "partial_update"]:
            return RealtorUpdateSerializer  # type: ignore
        if self.action == "stats":
            return RealtorStatsSerializer  # type: ignore
        return RealtorDetailSerializer  # type: ignore

    def get_queryset(self):  # type: ignore
        """Filter realtors by super_admin's agency."""
        user = self.request.user

        # Platform superusers see all realtors
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return super().get_queryset().filter(role=CustomUser.RoleChoices.REALTOR)
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return super().get_queryset().filter(role=CustomUser.RoleChoices.REALTOR)

        # Super admins see only their agency's realtors
        if hasattr(user, "is_super_admin") and user.is_super_admin():
            return super().get_queryset().filter(
                role=CustomUser.RoleChoices.REALTOR,
                agency=user.agency,
            )

        # No access for others
        return CustomUser.objects.none()

    def get_serializer_context(self) -> dict:  # type: ignore
        """Add agency to serializer context for realtor creation."""
        context = super().get_serializer_context()
        user = self.request.user

        # Set agency for realtor creation
        if hasattr(user, "agency") and user.agency:
            context["agency"] = user.agency

        return context

    def perform_create(self, serializer):  # type: ignore
        """Create realtor with agency assignment."""
        user = self.request.user

        # Check agency limits
        if hasattr(user, "agency") and user.agency:
            agency = user.agency
            current_realtors = agency.employees.filter(
                role=CustomUser.RoleChoices.REALTOR,
                is_active=True,
            ).count()

            if agency.realtors_limit > 0 and current_realtors >= agency.realtors_limit:
                from rest_framework.exceptions import ValidationError
                raise ValidationError(
                    {
                        "detail": f"Достигнут лимит риелторов для агентства "
                        f"({agency.realtors_limit}). Удалите неактивных или свяжитесь с поддержкой."
                    }
                )

        serializer.save()

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):  # type: ignore
        """
        Deactivate a realtor.

        POST /api/v1/super-admin/realtors/{id}/deactivate/

        Sets is_active=False, preventing login but preserving data.
        """
        realtor = self.get_object()

        # Check permission
        if not self.check_agency_ownership(realtor):
            return Response(
                {"detail": "Вы можете деактивировать только риелторов своего агентства."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not realtor.is_active:
            return Response(
                {"detail": "Риелтор уже деактивирован."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        realtor.is_active = False
        realtor.save(update_fields=["is_active"])

        return Response(
            {
                "message": f"Риелтор {realtor.email} деактивирован.",
                "realtor": RealtorDetailSerializer(realtor).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):  # type: ignore
        """
        Activate a realtor.

        POST /api/v1/super-admin/realtors/{id}/activate/

        Sets is_active=True, allowing login again.
        """
        realtor = self.get_object()

        # Check permission
        if not self.check_agency_ownership(realtor):
            return Response(
                {"detail": "Вы можете активировать только риелторов своего агентства."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if realtor.is_active:
            return Response(
                {"detail": "Риелтор уже активен."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        realtor.is_active = True
        realtor.save(update_fields=["is_active"])

        return Response(
            {
                "message": f"Риелтор {realtor.email} активирован.",
                "realtor": RealtorDetailSerializer(realtor).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="stats")
    def stats(self, request, pk=None):  # type: ignore
        """
        Get performance statistics for a realtor.

        GET /api/v1/super-admin/realtors/{id}/stats/?start=2025-01-01&end=2025-10-31

        Query params:
        - start (YYYY-MM-DD): Start date for period (optional)
        - end (YYYY-MM-DD): End date for period (optional)

        Returns bookings count, revenue, property stats for the realtor.
        """
        realtor = self.get_object()

        # Check permission
        if not self.check_agency_ownership(realtor):
            return Response(
                {"detail": "Вы можете просматривать статистику только риелторов своего агентства."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Parse date filters
        start_date = request.query_params.get("start")
        end_date = request.query_params.get("end")

        if start_date:
            start_date = date.fromisoformat(start_date)
        if end_date:
            end_date = date.fromisoformat(end_date)

        # Calculate stats
        stats_data = self._calculate_realtor_stats(realtor, start_date, end_date)

        serializer = RealtorStatsSerializer(stats_data)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def check_agency_ownership(self, realtor: CustomUser) -> bool:
        """Check if current user is owner of realtor's agency."""
        user = self.request.user

        # Platform superusers have full access
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return True

        # Check agency match
        return realtor.agency and realtor.agency == user.agency

    def _calculate_realtor_stats(
        self, realtor: CustomUser, start_date: date | None, end_date: date | None
    ) -> dict:  # type: ignore
        """Calculate performance statistics for a realtor."""
        from apps.bookings.models import Booking

        # Properties stats
        properties_qs = realtor.properties.all()
        properties_count = properties_qs.count()
        active_properties = properties_qs.filter(status="active").count()

        # Bookings stats
        bookings_qs = Booking.objects.filter(property__owner=realtor)

        # Apply date filters
        if start_date:
            bookings_qs = bookings_qs.filter(check_in__gte=start_date)
        if end_date:
            bookings_qs = bookings_qs.filter(check_out__lte=end_date)

        total_bookings = bookings_qs.count()
        confirmed_bookings = bookings_qs.filter(status=Booking.Status.CONFIRMED).count()
        completed_bookings = bookings_qs.filter(status=Booking.Status.COMPLETED).count()
        cancelled_bookings = bookings_qs.filter(
            status__in=[
                Booking.Status.CANCELLED_BY_GUEST,
                Booking.Status.CANCELLED_BY_REALTOR,
            ]
        ).count()

        # Revenue stats (only confirmed and completed)
        revenue_qs = bookings_qs.filter(
            status__in=[Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED],
            payment_status=Booking.PaymentStatus.PAID,
        )

        total_revenue = revenue_qs.aggregate(
            total=models.Sum("total_price")
        )["total"] or Decimal("0.00")

        average_booking_value = Decimal("0.00")
        if revenue_qs.count() > 0:
            average_booking_value = total_revenue / revenue_qs.count()

        return {
            "realtor_id": realtor.id,
            "realtor_name": realtor.username or realtor.email,
            "realtor_email": realtor.email,
            "properties_count": properties_count,
            "active_properties": active_properties,
            "total_bookings": total_bookings,
            "confirmed_bookings": confirmed_bookings,
            "completed_bookings": completed_bookings,
            "cancelled_bookings": cancelled_bookings,
            "total_revenue": total_revenue,
            "average_booking_value": average_booking_value,
            "period_start": start_date,
            "period_end": end_date,
        }


class AgencyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing agency details and analytics.

    Endpoints:
    - GET /api/v1/super-admin/agency/ - get current super_admin's agency
    - GET /api/v1/super-admin/agency/stats/ - agency-level statistics
    - GET /api/v1/super-admin/agency/top-performers/ - top realtors & properties
    """

    queryset = RealEstateAgency.objects.prefetch_related("employees", "properties").all()
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    serializer_class = AgencySerializer

    def get_queryset(self):  # type: ignore
        """Filter to current user's agency only."""
        user = self.request.user

        # Platform superusers see all agencies
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return super().get_queryset()
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return super().get_queryset()

        # Super admins see only their agency
        if hasattr(user, "agency") and user.agency:
            return super().get_queryset().filter(id=user.agency.id)

        return RealEstateAgency.objects.none()

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):  # type: ignore
        """
        Get agency-level statistics.

        GET /api/v1/super-admin/agency/stats/?start=2025-01-01&end=2025-10-31

        Query params:
        - start (YYYY-MM-DD): Start date for period (optional)
        - end (YYYY-MM-DD): End date for period (optional)

        Returns aggregated stats for all realtors in the agency.
        """
        user = request.user

        # Get agency
        if hasattr(user, "agency") and user.agency:
            agency = user.agency
        else:
            return Response(
                {"detail": "У вас нет привязанного агентства."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse date filters
        start_date = request.query_params.get("start")
        end_date = request.query_params.get("end")

        if start_date:
            start_date = date.fromisoformat(start_date)
        if end_date:
            end_date = date.fromisoformat(end_date)

        # Calculate stats
        stats_data = self._calculate_agency_stats(agency, start_date, end_date)

        serializer = AgencyStatsSerializer(stats_data)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="top-performers")
    def top_performers(self, request):  # type: ignore
        """
        Get top-performing realtors and properties.

        GET /api/v1/super-admin/agency/top-performers/?limit=5&period=30

        Query params:
        - limit (int): Number of top items to return (default 5)
        - period (int): Days to look back (default 30)

        Returns:
        - Top realtors by revenue
        - Top properties by bookings count
        """
        user = request.user

        # Get agency
        if hasattr(user, "agency") and user.agency:
            agency = user.agency
        else:
            return Response(
                {"detail": "У вас нет привязанного агентства."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse params
        limit = int(request.query_params.get("limit", 5))
        period_days = int(request.query_params.get("period", 30))

        start_date = timezone.now().date() - timedelta(days=period_days)

        # Get top realtors
        from apps.bookings.models import Booking

        realtors = agency.employees.filter(role=CustomUser.RoleChoices.REALTOR, is_active=True)

        # Calculate revenue per realtor
        realtor_stats = []
        for realtor in realtors:
            revenue = Booking.objects.filter(
                property__owner=realtor,
                check_in__gte=start_date,
                status__in=[
                    Booking.Status.CONFIRMED,
                    Booking.Status.IN_PROGRESS,
                    Booking.Status.COMPLETED,
                ],
                payment_status=Booking.PaymentStatus.PAID,
            ).aggregate(total=models.Sum("total_price"))["total"] or Decimal("0.00")

            realtor_stats.append({
                "realtor_id": realtor.id,
                "realtor_name": realtor.username or realtor.email,
                "realtor_email": realtor.email,
                "revenue": float(revenue),
            })

        # Sort by revenue
        top_realtors = sorted(realtor_stats, key=lambda x: x["revenue"], reverse=True)[:limit]

        # Get top properties
        properties = agency.properties.filter(status="active")

        property_stats = []
        for prop in properties:
            bookings_count = Booking.objects.filter(
                property=prop,
                check_in__gte=start_date,
                status__in=[
                    Booking.Status.CONFIRMED,
                    Booking.Status.IN_PROGRESS,
                    Booking.Status.COMPLETED,
                ],
            ).count()

            if bookings_count > 0:
                property_stats.append({
                    "property_id": prop.id,
                    "property_title": prop.title,
                    "owner_email": prop.owner.email,
                    "bookings_count": bookings_count,
                })

        # Sort by bookings count
        top_properties = sorted(property_stats, key=lambda x: x["bookings_count"], reverse=True)[:limit]

        return Response(
            {
                "period_days": period_days,
                "start_date": start_date,
                "top_realtors": top_realtors,
                "top_properties": top_properties,
            },
            status=status.HTTP_200_OK,
        )

    def _calculate_agency_stats(
        self, agency: RealEstateAgency, start_date: date | None, end_date: date | None
    ) -> dict:  # type: ignore
        """Calculate agency-level statistics."""
        from apps.bookings.models import Booking

        # Realtors stats
        realtors = agency.employees.filter(role=CustomUser.RoleChoices.REALTOR)
        total_realtors = realtors.count()
        active_realtors = realtors.filter(is_active=True).count()

        # Properties stats
        properties = agency.properties.all()
        total_properties = properties.count()
        active_properties = properties.filter(status="active").count()

        # Bookings stats
        bookings_qs = Booking.objects.filter(agency=agency)

        # Apply date filters
        if start_date:
            bookings_qs = bookings_qs.filter(check_in__gte=start_date)
        if end_date:
            bookings_qs = bookings_qs.filter(check_out__lte=end_date)

        total_bookings = bookings_qs.count()
        confirmed_bookings = bookings_qs.filter(status=Booking.Status.CONFIRMED).count()
        completed_bookings = bookings_qs.filter(status=Booking.Status.COMPLETED).count()

        # Revenue stats
        revenue_qs = bookings_qs.filter(
            status__in=[Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED],
            payment_status=Booking.PaymentStatus.PAID,
        )

        total_revenue = revenue_qs.aggregate(
            total=models.Sum("total_price")
        )["total"] or Decimal("0.00")

        average_booking_value = Decimal("0.00")
        if revenue_qs.count() > 0:
            average_booking_value = total_revenue / revenue_qs.count()

        return {
            "agency_id": agency.id,
            "agency_name": agency.name,
            "total_realtors": total_realtors,
            "active_realtors": active_realtors,
            "total_properties": total_properties,
            "active_properties": active_properties,
            "total_bookings": total_bookings,
            "confirmed_bookings": confirmed_bookings,
            "completed_bookings": completed_bookings,
            "total_revenue": total_revenue,
            "average_booking_value": average_booking_value,
        }