"""URL routing for the reviews domain."""

from django.urls import include, path  # type: ignore
from rest_framework.routers import DefaultRouter  # type: ignore

from .views import ReviewViewSet

router = DefaultRouter()
router.register(r'reviews', ReviewViewSet, basename='review')

urlpatterns = [path('', include(router.urls))]