from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, UserProfileViewSet, login_view, TelegramRegisterLoginView # Add TelegramRegisterLoginView

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'profiles', UserProfileViewSet, basename='userprofile') # Added basename

urlpatterns = [
    path('', include(router.urls)),
    path('login/', login_view, name='login'), # Standard JWT login
    path('telegram_auth/register_or_login/', TelegramRegisterLoginView.as_view(), name='telegram_register_login'), # New endpoint
]
