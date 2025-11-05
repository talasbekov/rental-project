"""URL routing for the finance domain."""

from __future__ import annotations

from django.urls import include, path  # type: ignore
from rest_framework.routers import DefaultRouter  # type: ignore

from .views import PaymentViewSet

router = DefaultRouter()
router.register(r"", PaymentViewSet, basename="payment")

urlpatterns = [
    path("", include(router.urls)),
]
