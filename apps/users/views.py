"""REST API views for authentication flows."""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import generics, permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PasswordResetToken
from .serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)


def _issue_tokens_for_user(user) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class RegisterView(generics.CreateAPIView):
    """Registers a new user and returns JWT pair."""

    serializer_class = RegisterSerializer
    permission_classes = (permissions.AllowAny,)
    created_user = None

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # type: ignore[override]
        response = super().create(request, *args, **kwargs)
        user = self.created_user
        tokens = _issue_tokens_for_user(user)
        response.data = {
            "user": UserSerializer(user).data,
            "tokens": tokens,
        }
        return response

    def perform_create(self, serializer):  # type: ignore[override]
        self.created_user = serializer.save()


class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        tokens = _issue_tokens_for_user(user)
        return Response({"user": UserSerializer(user).data, "tokens": tokens})


class PasswordResetRequestView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token: PasswordResetToken = serializer.save()

        # Stub for email delivery; replace with notification service later.
        logger.info(
            "Password reset code generated for user_id=%s code=%s (expires at %s)",
            token.user_id,
            token.code,
            token.expires_at,
        )

        delivery_channel = "email" if "@" in serializer.validated_data["identifier"] else "sms"
        return Response(
            {
                "detail": f"Код отправлен через {delivery_channel}. Действует 15 минут.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Пароль обновлен."}, status=status.HTTP_200_OK)
