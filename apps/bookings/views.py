"""API views for the booking domain."""

from __future__ import annotations

from rest_framework import permissions, status, viewsets  # type: ignore
from rest_framework.decorators import action  # type: ignore
from rest_framework.response import Response  # type: ignore

from .models import Booking
from .services import reserve_dates_for_booking, release_dates_for_booking
from .serializers import BookingCreateSerializer, BookingSerializer


class IsBookingStakeholder(permissions.BasePermission):
    """Гости, владельцы объектов и администраторы имеют доступ к бронированию."""

    def has_object_permission(self, request, view, obj: Booking):  # type: ignore
        user = request.user
        if not user.is_authenticated:
            return False
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return True
        if hasattr(user, "is_super_admin") and user.is_super_admin():
            return obj.agency_id == getattr(user.agency, "id", None)
        if hasattr(user, "is_realtor") and user.is_realtor():
            return obj.property.owner_id == user.id
        return obj.guest_id == user.id


class BookingViewSet(viewsets.ModelViewSet):
    """Viewset для создания и управления бронированиями."""

    queryset = Booking.objects.select_related("property", "guest", "property__owner", "agency").all()
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsBookingStakeholder]

    def get_serializer_class(self):  # type: ignore
        if self.action == "create":
            return BookingCreateSerializer
        return BookingSerializer

    def get_queryset(self):  # type: ignore
        user = self.request.user
        qs = super().get_queryset()
        if not user.is_authenticated:
            return qs.none()
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return qs
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return qs
        if hasattr(user, "is_super_admin") and user.is_super_admin():
            return qs.filter(agency=user.agency)
        if hasattr(user, "is_realtor") and user.is_realtor():
            return qs.filter(property__owner=user)
        return qs.filter(guest=user)

    def create(self, request, *args, **kwargs):  # type: ignore
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        reserve_dates_for_booking(booking)
        try:
            from .tasks import schedule_hold_expiration  # type: ignore

            hold_timeout = 15 * 60
            schedule_hold_expiration.apply_async(args=[booking.id], countdown=hold_timeout)
        except Exception:
            pass
        read_serializer = BookingSerializer(booking, context=self.get_serializer_context())
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=["post"], permission_classes=[IsBookingStakeholder])
    def cancel(self, request, pk=None):  # type: ignore
        booking: Booking = self.get_object()  # type: ignore
        user = request.user
        if booking.status in [Booking.Status.COMPLETED, Booking.Status.EXPIRED]:
            return Response(
                {"detail": "Нельзя отменить завершённое или истекшее бронирование."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if hasattr(user, "is_realtor") and user.is_realtor() and booking.property.owner_id == user.id:
            booking.mark_cancelled(Booking.CancellationSource.REALTOR, request.data.get("reason", ""))
        elif booking.guest_id == user.id:
            booking.mark_cancelled(Booking.CancellationSource.GUEST, request.data.get("reason", ""))
        elif hasattr(user, "is_super_admin") and user.is_super_admin():
            booking.mark_cancelled(Booking.CancellationSource.REALTOR, request.data.get("reason", ""))
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)
        release_dates_for_booking(booking)
        return Response({"status": booking.status}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], permission_classes=[IsBookingStakeholder])
    def confirm_payment(self, request, pk=None):  # type: ignore
        booking: Booking = self.get_object()  # type: ignore
        if booking.payment_status == Booking.PaymentStatus.PAID:
            return Response({"detail": "Оплата уже подтверждена."}, status=status.HTTP_400_BAD_REQUEST)
        booking.mark_paid()
        return Response({"status": booking.status, "payment_status": booking.payment_status})
