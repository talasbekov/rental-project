from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from .models import UserProfile  # Assuming UserProfile is in the same app 'users'

User = get_user_model()


class UserAuthTests(APITestCase):
    def setUp(self):
        self.username = "testuser"
        self.password = "testpass123"
        self.user = User.objects.create_user(
            username=self.username, password=self.password
        )
        # Ensure UserProfile is created for the user, as your serializer/view might depend on it
        UserProfile.objects.create(
            user=self.user, role="user", phone_number="+1234567890"
        )

        self.register_url = reverse(
            "user-list"
        )  # Assumes 'user-list' is the basename for UserViewSet create action
        self.login_url = reverse("login")  # From users.urls

    def test_user_registration(self):
        data = {
            "username": "newuser",
            "password": "newpassword123",
            "email": "newuser@example.com",
            "profile": {  # Nested profile data
                "role": "user",
                "phone_number": "+9876543210",
            },
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="newuser").exists())
        self.assertTrue(
            UserProfile.objects.filter(
                user__username="newuser", phone_number="+9876543210"
            ).exists()
        )

    def test_user_login_success(self):
        data = {"username": self.username, "password": self.password}
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_user_login_failure_invalid_credentials(self):
        data = {"username": self.username, "password": "wrongpassword"}
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
