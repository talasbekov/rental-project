"""URL routing for favorites."""

from django.urls import include, path  # type: ignore
from rest_framework.routers import DefaultRouter  # type: ignore

from .views import FavoriteViewSet

router = DefaultRouter()
router.register(r'', FavoriteViewSet, basename='favorite')

urlpatterns = [path('', include(router.urls))]
