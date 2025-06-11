from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes as decorator_permission_classes
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
from django.contrib.auth import authenticate # We still need this for custom view

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action == 'create': # Registration
            self.permission_classes = [AllowAny,]
        # For other actions, the default 'IsAuthenticated' (set in settings.py) will apply.
        return super(UserViewSet, self).get_permissions()

class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    # Default 'IsAuthenticated' will apply.

@api_view(['POST'])
@decorator_permission_classes([AllowAny])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(username=username, password=password)

    if user:
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })
    else:
        return Response({'error': 'Invalid Credentials'}, status=status.HTTP_400_BAD_REQUEST)

# We could also use SimpleJWT's provided TokenObtainPairView by adding it to urls.py
# e.g., path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
# path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
# This custom login_view provides similar functionality for access/refresh tokens.
