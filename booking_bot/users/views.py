from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import (
    api_view,
    permission_classes as decorator_permission_classes,
)
from rest_framework.permissions import AllowAny
from django.contrib.auth.models import User

# Remove authenticate from django.contrib.auth as simplejwt handles it or we do it manually for its views
# from django.contrib.auth import authenticate # Not needed if using simplejwt views directly
# from rest_framework.authtoken.models import Token # Not needed

from .models import UserProfile
from .serializers import UserSerializer, UserProfileSerializer

# Import SimpleJWT views or components
from rest_framework_simplejwt.tokens import RefreshToken

# For a custom login view:
from django.contrib.auth import authenticate  # We still need this for custom view

# Add these imports
from .serializers import (
    UserSerializer,
    UserProfileSerializer,
    TelegramUserSerializer,
)  # Add TelegramUserSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth.models import User
from .models import UserProfile
from django.db import transaction
import logging  # Recommended to add logger for views

logger = logging.getLogger(__name__)  # Recommended: get a logger for the view


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action == "create":  # Registration
            self.permission_classes = [
                AllowAny,
            ]
        # For other actions, the default 'IsAuthenticated' (set in settings.py) will apply.
        return super(UserViewSet, self).get_permissions()


class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    # Default 'IsAuthenticated' will apply.


@api_view(["POST"])
@decorator_permission_classes([AllowAny])
def login_view(request):
    username = request.data.get("username")
    password = request.data.get("password")

    user = authenticate(username=username, password=password)

    if user:
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }
        )
    else:
        return Response(
            {"error": "Invalid Credentials"}, status=status.HTTP_400_BAD_REQUEST
        )


# We could also use SimpleJWT's provided TokenObtainPairView by adding it to urls.py
# e.g., path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
# path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
# This custom login_view provides similar functionality for access/refresh tokens.


class TelegramRegisterLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = TelegramUserSerializer(data=request.data)
        if serializer.is_valid():
            validated_data = serializer.validated_data
            telegram_chat_id = str(
                validated_data["telegram_chat_id"]
            )  # Ensure it's a string

            try:
                with transaction.atomic():
                    # 1) Ensure the User exists (lookup by a unique username derived from telegram_chat_id)
                    user, user_created = User.objects.get_or_create(
                        username=f"telegram_{telegram_chat_id}",
                        defaults={
                            "first_name": validated_data.get("first_name", ""),
                            "last_name": validated_data.get("last_name", ""),
                        },
                    )
                    if user_created:
                        user.set_unusable_password()
                        user.save()

                    # 2) Now create or update the UserProfile, using the FK 'user' as the lookup
                    profile_defaults = {
                        "telegram_chat_id": telegram_chat_id,
                        "phone_number": validated_data.get("phone_number"),
                        "role": "user",
                    }
                    user_profile, profile_created = (
                        UserProfile.objects.update_or_create(
                            user=user, defaults=profile_defaults
                        )
                    )

                refresh = RefreshToken.for_user(user_profile.user)
                return Response(
                    {
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                        "user_id": user_profile.user.id,
                        "profile_id": user_profile.id,
                        "created": profile_created,
                    },
                    status=status.HTTP_200_OK,
                )

            except Exception as e:
                logger.error(f"Error in TelegramRegisterLoginView: {e}", exc_info=True)
                return Response(
                    {"error": "Server error during registration/login."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
