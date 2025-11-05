"""API views for managing reviews."""

from __future__ import annotations

from django.db import models  # type: ignore
from django.utils import timezone  # type: ignore
from rest_framework import viewsets, permissions, status, serializers  # type: ignore
from rest_framework.decorators import action  # type: ignore
from rest_framework.response import Response  # type: ignore

from .models import Review
from .serializers import ReviewSerializer, ReviewCreateSerializer, RealtorResponseSerializer


class IsReviewerOrAdmin(permissions.BasePermission):
    """Allow guests to manage their reviews and admins to manage all."""

    def has_object_permission(self, request, view, obj: Review) -> bool:  # type: ignore
        user = request.user
        if not user.is_authenticated:
            return False
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return True
        if hasattr(user, "is_super_admin") and user.is_super_admin():
            return obj.property.agency_id == getattr(user.agency, "id", None)
        if hasattr(user, "is_realtor") and user.is_realtor():
            return obj.property.owner_id == user.id
        return obj.user_id == user.id


class ReviewViewSet(viewsets.ModelViewSet):
    """Viewset for creating, retrieving and deleting reviews."""

    queryset = Review.objects.select_related('property', 'user', 'booking').all()
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsReviewerOrAdmin]

    def get_serializer_class(self) -> type[ReviewSerializer]:  # type: ignore
        if self.action == 'create':
            return ReviewCreateSerializer  # type: ignore
        if self.action == 'respond':
            return RealtorResponseSerializer  # type: ignore
        return ReviewSerializer  # type: ignore

    def get_queryset(self):  # type: ignore
        qs = super().get_queryset()
        user = self.request.user

        # Фильтрация по property_id (query param)
        property_id = self.request.query_params.get('property', None)
        if property_id:
            qs = qs.filter(property_id=property_id)

        # Только одобренные отзывы для неавторизованных
        if not user.is_authenticated:
            return qs.filter(is_approved=True)

        # Админы видят все
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return qs
        if hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            return qs

        # Супер админ видит отзывы для объектов своего агентства
        if hasattr(user, "is_super_admin") and user.is_super_admin():
            return qs.filter(property__agency=user.agency)

        # Риелтор видит отзывы для своих объектов
        if hasattr(user, "is_realtor") and user.is_realtor():
            return qs.filter(property__owner=user)

        # Обычный пользователь видит свои отзывы + одобренные чужие
        return qs.filter(models.Q(user=user) | models.Q(is_approved=True))

    def perform_create(self, serializer):  # type: ignore
        """Создание отзыва с валидацией бронирования."""
        from apps.bookings.models import Booking

        user = self.request.user
        property_id = serializer.validated_data['property'].id
        booking_id = serializer.validated_data.get('booking')

        # Проверяем, есть ли завершенное бронирование для этого объекта
        if booking_id:
            try:
                booking = Booking.objects.get(
                    id=booking_id.id,
                    guest=user,
                    property_id=property_id,
                    status=Booking.Status.COMPLETED
                )
            except Booking.DoesNotExist:
                raise serializers.ValidationError(
                    "Отзыв можно оставить только для завершенного бронирования."
                )
        else:
            # Ищем любое завершенное бронирование этого пользователя для этого объекта
            booking = Booking.objects.filter(
                guest=user,
                property_id=property_id,
                status=Booking.Status.COMPLETED
            ).first()

            if not booking:
                raise serializers.ValidationError(
                    "Вы можете оставить отзыв только после завершения бронирования."
                )

        serializer.save(user=user, booking=booking)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def respond(self, request, pk=None):  # type: ignore
        """Ответ риелтора на отзыв."""
        review = self.get_object()
        user = request.user

        # Проверяем, что это владелец объекта
        if review.property.owner_id != user.id:
            return Response(
                {"detail": "Только владелец объекта может отвечать на отзывы."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = RealtorResponseSerializer(data=request.data)
        if serializer.is_valid():
            review.realtor_response = serializer.validated_data['realtor_response']
            review.realtor_response_at = timezone.now()
            review.save(update_fields=['realtor_response', 'realtor_response_at'])

            return Response(
                ReviewSerializer(review).data,
                status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
