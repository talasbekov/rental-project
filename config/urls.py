from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include(("apps.users.urls", "auth"), namespace="auth")),
    path("api/v1/properties/", include(("apps.properties.urls", "properties"), namespace="properties")),
    path("api/v1/bookings/", include(("apps.bookings.urls", "bookings"), namespace="bookings")),
]
