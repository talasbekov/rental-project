"""API tests for authentication endpoints."""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import PasswordResetToken, User


class AuthAPITests(APITestCase):
    def test_register_returns_tokens(self) -> None:
        payload = {
            "email": "guest@example.com",
            "phone": "+77001234567",
            "first_name": "Guest",
            "last_name": "User",
            "password": "StrongPass123",
            "password_confirm": "StrongPass123",
        }

        response = self.client.post(reverse("auth:register"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIn("tokens", response.data)
        self.assertEqual(response.data["user"]["email"], payload["email"])
        self.assertTrue(User.objects.filter(email=payload["email"]).exists())

    def test_login_limited_attempts(self) -> None:
        user = User.objects.create_user(
            email="lock@example.com",
            phone="+77777777777",
            password="CorrectPassword1",
        )

        url = reverse("auth:login")
        wrong_payload = {"login": user.email, "password": "wrong"}
        for _ in range(5):
            response = self.client.post(url, wrong_payload, format="json")

        user.refresh_from_db()
        self.assertTrue(user.is_locked)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # After lock expires user can login again
        user.locked_until = timezone.now() - timedelta(minutes=1)
        user.save(update_fields=["locked_until"])
        response = self.client.post(url, {"login": user.email, "password": "CorrectPassword1"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_password_reset_flow(self) -> None:
        user = User.objects.create_user(
            email="reset@example.com",
            phone="+77000000000",
            password="OldPassword1",
        )

        request_resp = self.client.post(
            reverse("auth:password-reset-request"),
            {"identifier": user.email},
            format="json",
        )
        self.assertEqual(request_resp.status_code, status.HTTP_202_ACCEPTED, request_resp.data)

        token = PasswordResetToken.objects.get(user=user)
        confirm_payload = {
            "identifier": user.email,
            "code": token.code,
            "new_password": "NewPassword1",
            "new_password_confirm": "NewPassword1",
        }
        confirm_resp = self.client.post(
            reverse("auth:password-reset-confirm"),
            confirm_payload,
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.data)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPassword1"))
