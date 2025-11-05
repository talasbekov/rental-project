"""URL routing for authentication endpoints (namespace: auth)."""

from __future__ import annotations

from django.urls import path  # type: ignore
from rest_framework_simplejwt.views import TokenRefreshView  # type: ignore

from .auth_views import (
    RegisterView,
    LoginView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
)

app_name = "auth"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("password-reset/request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
]

