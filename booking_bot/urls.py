from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('whatsapp/', include('booking_bot.whatsapp_bot.urls')),

    path('admin/', admin.site.urls),
    path('api/v1/', include('booking_bot.users.urls')),
    path('api/v1/', include('booking_bot.listings.urls')),
    path('api/v1/', include('booking_bot.bookings.urls')),
    path('api/v1/', include('booking_bot.payments.urls')),
    # It's generally better to have distinct base paths for different apps if they don't naturally nest,
    # e.g., /api/v1/users/, /api/v1/listings/ etc.
    # For now, this will make them all available under /api/v1/
    # The routers within each app will provide /users/, /properties/ etc.
]
