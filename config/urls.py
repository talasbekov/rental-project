"""URL configuration for ZhilyeGO project.

The `urlpatterns` list routes URLs to views. It includes both Django admin
and application‑level routers provided by Django Rest Framework and each app.
"""
from django.contrib import admin  # type: ignore
from django.urls import path, include  # type: ignore

# API versioning. v1 is our initial version; future versions can be added here.

urlpatterns = [
    path('admin/', admin.site.urls),
    # Application URLs
    path('api/v1/auth/', include(('apps.users.auth_urls', 'auth'), namespace='auth')),
    path('api/v1/users/', include('apps.users.urls')),
    path('api/v1/properties/', include('apps.properties.urls')),
    path('api/v1/bookings/', include('apps.bookings.urls')),
    path('api/v1/finances/', include('apps.finances.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    path('api/v1/analytics/', include('apps.analytics.urls')),
    path('api/v1/reviews/', include('apps.reviews.urls')),
    path('api/v1/favorites/', include('apps.favorites.urls')),
    # Super Admin API
    path('api/v1/super-admin/', include('apps.users.api.urls')),
    # Telegram Bot Webhook
    path('telegram/', include('apps.telegrambot.urls')),
]
