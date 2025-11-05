"""API views for favorites management."""

from __future__ import annotations

from django.db import IntegrityError  # type: ignore
from django.db.models import Prefetch  # type: ignore
from rest_framework import viewsets, permissions, status  # type: ignore
from rest_framework.decorators import action  # type: ignore
from rest_framework.response import Response  # type: ignore

from apps.properties.models import Property
from .models import Favorite
from .serializers import (
    FavoriteSerializer,
    FavoriteCreateSerializer,
    FavoriteToggleSerializer,
    FavoriteBulkDeleteSerializer,
)


class FavoriteViewSet(viewsets.ModelViewSet):
    """
    Viewset to add, list and remove favorite properties.

    Endpoints:
    - GET /api/v1/favorites/ - список избранных
    - POST /api/v1/favorites/ - добавить в избранное
    - DELETE /api/v1/favorites/{id}/ - удалить из избранного
    - POST /api/v1/favorites/toggle/ - переключить (добавить/удалить)
    - POST /api/v1/favorites/bulk_delete/ - массовое удаление
    - GET /api/v1/favorites/check/{property_id}/ - проверить наличие в избранном
    """

    queryset = Favorite.objects.select_related('user', 'property').all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self) -> type[FavoriteSerializer]:  # type: ignore
        if self.action == 'create':
            return FavoriteCreateSerializer  # type: ignore
        if self.action == 'toggle':
            return FavoriteToggleSerializer  # type: ignore
        if self.action == 'bulk_delete':
            return FavoriteBulkDeleteSerializer  # type: ignore
        return FavoriteSerializer  # type: ignore

    def get_queryset(self):  # type: ignore
        """Пользователи видят только свои избранные."""
        qs = super().get_queryset().filter(user=self.request.user)

        # Prefetch related data для оптимизации
        qs = qs.prefetch_related(
            Prefetch('property__reviews'),
            'property__photos',
        )

        # Фильтрация по city
        city = self.request.query_params.get('city', None)
        if city:
            qs = qs.filter(property__city__icontains=city)

        # Фильтрация по district
        district = self.request.query_params.get('district', None)
        if district:
            qs = qs.filter(property__district__icontains=district)

        # Фильтрация по price range
        min_price = self.request.query_params.get('min_price', None)
        max_price = self.request.query_params.get('max_price', None)
        if min_price:
            qs = qs.filter(property__base_price__gte=min_price)
        if max_price:
            qs = qs.filter(property__base_price__lte=max_price)

        # Только активные объекты
        qs = qs.filter(property__status='active')

        return qs

    def perform_create(self, serializer):  # type: ignore
        """Добавление в избранное с обработкой дубликатов."""
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            # Объект уже в избранном
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                {"detail": "Этот объект уже в избранном."}
            )

    def create(self, request, *args, **kwargs):  # type: ignore
        """Переопределенный create для возврата детальной информации."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
        except Exception as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Возвращаем полную информацию о созданном избранном
        favorite = Favorite.objects.select_related('property').prefetch_related(
            'property__reviews', 'property__photos'
        ).get(
            user=request.user,
            property=serializer.validated_data['property']
        )

        output_serializer = FavoriteSerializer(favorite)
        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=['post'], url_path='toggle')
    def toggle(self, request):  # type: ignore
        """
        Переключение избранного (добавить/удалить).

        POST /api/v1/favorites/toggle/
        Body: {"property_id": 123}

        Returns:
            {"action": "added" | "removed", "favorite": {...} | null}
        """
        serializer = FavoriteToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        property_id = serializer.validated_data['property_id']
        user = request.user

        # Проверяем существование
        try:
            favorite = Favorite.objects.get(user=user, property_id=property_id)
            # Существует - удаляем
            favorite.delete()
            return Response(
                {
                    "action": "removed",
                    "property_id": property_id,
                    "message": "Объект удален из избранного"
                },
                status=status.HTTP_200_OK
            )
        except Favorite.DoesNotExist:
            # Не существует - добавляем
            property_obj = Property.objects.get(id=property_id)
            favorite = Favorite.objects.create(user=user, property=property_obj)

            # Возвращаем детальную информацию
            favorite = Favorite.objects.select_related('property').prefetch_related(
                'property__reviews', 'property__photos'
            ).get(id=favorite.id)

            return Response(
                {
                    "action": "added",
                    "favorite": FavoriteSerializer(favorite).data,
                    "message": "Объект добавлен в избранное"
                },
                status=status.HTTP_201_CREATED
            )

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):  # type: ignore
        """
        Массовое удаление избранных.

        POST /api/v1/favorites/bulk-delete/
        Body: {"favorite_ids": [1, 2, 3]}

        Returns:
            {"deleted": 3, "message": "..."}
        """
        serializer = FavoriteBulkDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        favorite_ids = serializer.validated_data['favorite_ids']
        user = request.user

        # Удаляем только избранные текущего пользователя
        deleted_count, _ = Favorite.objects.filter(
            id__in=favorite_ids,
            user=user
        ).delete()

        return Response(
            {
                "deleted": deleted_count,
                "message": f"Удалено {deleted_count} избранных"
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'], url_path='check/(?P<property_id>[0-9]+)')
    def check(self, request, property_id=None):  # type: ignore
        """
        Проверка наличия объекта в избранном.

        GET /api/v1/favorites/check/123/

        Returns:
            {"is_favorite": true/false, "favorite_id": 456 | null}
        """
        user = request.user

        try:
            favorite = Favorite.objects.get(user=user, property_id=property_id)
            return Response(
                {
                    "is_favorite": True,
                    "favorite_id": favorite.id
                },
                status=status.HTTP_200_OK
            )
        except Favorite.DoesNotExist:
            return Response(
                {
                    "is_favorite": False,
                    "favorite_id": None
                },
                status=status.HTTP_200_OK
            )

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):  # type: ignore
        """
        Статистика по избранным пользователя.

        GET /api/v1/favorites/stats/

        Returns:
            {"total": 15, "by_city": {...}, "average_price": ...}
        """
        user = request.user
        favorites = Favorite.objects.filter(user=user)

        total = favorites.count()

        # Группировка по городам
        from django.db.models import Count, Avg  # type: ignore

        by_city = favorites.values('property__city').annotate(
            count=Count('id')
        ).order_by('-count')

        # Средняя цена
        avg_price = favorites.aggregate(
            avg_price=Avg('property__base_price')
        )['avg_price']

        return Response(
            {
                "total": total,
                "by_city": list(by_city),
                "average_price": round(avg_price, 2) if avg_price else 0
            },
            status=status.HTTP_200_OK
        )