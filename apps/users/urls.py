"""URL declarations for the users app."""

from __future__ import annotations

from django.urls import path, include  # type: ignore
from rest_framework.routers import DefaultRouter  # type: ignore

from .views import UserViewSet

router = DefaultRouter()
router.register(r'', UserViewSet, basename='user')

urlpatterns = [
    path('', include(router.urls)),
]
