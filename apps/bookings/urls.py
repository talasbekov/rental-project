"""Routes for booking operations."""

from django.urls import path

from .views import BookingCancelView, BookingDetailView, BookingListCreateView, ReviewListCreateView

app_name = "bookings"

urlpatterns = [
    path("", BookingListCreateView.as_view(), name="list-create"),
    path("<uuid:pk>/", BookingDetailView.as_view(), name="detail"),
    path("<uuid:pk>/cancel/", BookingCancelView.as_view(), name="cancel"),
    path("reviews/", ReviewListCreateView.as_view(), name="reviews"),
]
