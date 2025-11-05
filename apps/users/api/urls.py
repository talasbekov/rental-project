"""URL routing for Super Admin API."""

from django.urls import path, include  # type: ignore
from rest_framework.routers import DefaultRouter  # type: ignore

from .views import RealtorViewSet, AgencyViewSet

# Create router
router = DefaultRouter()

# Register viewsets
router.register(r"realtors", RealtorViewSet, basename="superadmin-realtor")
router.register(r"agency", AgencyViewSet, basename="superadmin-agency")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
]