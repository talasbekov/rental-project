"""Views for authentication flows (register, login, token refresh, password reset)."""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken  # type: ignore

from .auth_serializers import (
    RegisterSerializer,
    LoginSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)
from .serializers import UserSerializer


def _tokens_for_user(user) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):  # type: ignore
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        data = {
            "user": UserSerializer(user).data,
            "tokens": _tokens_for_user(user),
        }
        return Response(data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):  # type: ignore
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        data = {
            "user": UserSerializer(user).data,
            "tokens": _tokens_for_user(user),
        }
        return Response(data, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):  # type: ignore
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Код отправлен на email, если пользователь найден."}, status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):  # type: ignore
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Пароль обновлён."}, status=status.HTTP_200_OK)

