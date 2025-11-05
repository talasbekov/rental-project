"""URL routing for the booking domain."""

from __future__ import annotations

from django.urls import include, path  # type: ignore
from rest_framework.routers import DefaultRouter  # type: ignore

from .views import BookingViewSet

router = DefaultRouter()
router.register(r"", BookingViewSet, basename="booking")

urlpatterns = [
    path("", include(router.urls)),
]
