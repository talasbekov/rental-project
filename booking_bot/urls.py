from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # API v1 paths
    path("api/v1/", include("booking_bot.users.urls")),
    path("api/v1/", include("booking_bot.listings.urls")),
    path("api/v1/", include("booking_bot.bookings.urls")),
    path(
        "api/v1/", include("booking_bot.payments.urls")
    ),  # Assuming payments might have API endpoints later
    # WhatsApp bot webhook path
    path("whatsapp/", include("booking_bot.whatsapp_bot.urls")),
    # Telegram bot webhook path
    path("telegram/", include("booking_bot.telegram_bot.urls")),
    # drf-spectacular URLs
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/v1/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/v1/schema/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Добавляем обслуживание медиа файлов для разработки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
