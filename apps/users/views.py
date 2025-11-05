"""User API views."""

from __future__ import annotations

from django.contrib.auth import get_user_model  # type: ignore
from rest_framework import permissions, status, viewsets  # type: ignore
from rest_framework.decorators import action  # type: ignore
from rest_framework.response import Response  # type: ignore

from .serializers import RegisterSerializer, UserSerializer

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """Управление пользователями.

    - `register` доступен без авторизации (гость -> пользователь)
    - `me` возвращает профиль текущего пользователя
    - операции списка/редактирования доступны только персоналу платформы
    """

    serializer_class = UserSerializer
    queryset = User.objects.select_related("agency").all()

    def get_permissions(self):  # type: ignore
        if self.action in {"register"}:
            return [permissions.AllowAny()]
        if self.action in {"me", "partial_update", "update"}:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

    def list(self, request, *args, **kwargs):  # type: ignore
        """Ограничиваем стандартный список только персоналом."""
        return super().list(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):  # type: ignore
        # Администраторы могут обновлять произвольных пользователей, остальные только себя.
        if not request.user.is_staff and str(request.user.pk) != str(kwargs.get("pk")):
            return Response(status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):  # type: ignore
        if not request.user.is_staff and str(request.user.pk) != str(kwargs.get("pk")):
            return Response(status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=["post"], permission_classes=[permissions.AllowAny])
    def register(self, request):
        """Регистрация нового пользователя (гостя)."""
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        """Возвращает профиль текущего пользователя."""
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
