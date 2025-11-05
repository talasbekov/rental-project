"""URL routing for notifications."""

from django.urls import include, path  # type: ignore
from rest_framework.routers import DefaultRouter  # type: ignore

from .views import NotificationViewSet

router = DefaultRouter()
router.register(r'', NotificationViewSet, basename='notification')

urlpatterns = [path('', include(router.urls))]
