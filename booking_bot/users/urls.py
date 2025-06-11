from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, UserProfileViewSet, login_view

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user') # Added basename
router.register(r'profiles', UserProfileViewSet, basename='userprofile') # Added basename

urlpatterns = [
    path('', include(router.urls)),
    path('login/', login_view, name='login'),
]
