from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BookingViewSet, UserBookingsListView # Add UserBookingsListView

router = DefaultRouter()
router.register(r'bookings', BookingViewSet, basename='booking') # Added basename for clarity

urlpatterns = [
    path('', include(router.urls)),
    path('my-bookings/', UserBookingsListView.as_view(), name='user-bookings-list'), # New line
]
