"""URL routing for analytics endpoints."""

from django.urls import path  # type: ignore

from .views import OverviewAnalyticsView


urlpatterns = [
    # Do not prefix with 'analytics/' here; the namespace is defined in config.urls
    path('overview/', OverviewAnalyticsView.as_view(), name='analytics-overview'),
]