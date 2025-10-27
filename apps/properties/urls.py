"""Routes for property catalog."""

from django.urls import path

from .views import FavoriteDeleteView, FavoriteListCreateView, PropertyDetailView, PropertyListView

app_name = "properties"

urlpatterns = [
    path("", PropertyListView.as_view(), name="list"),
    path("<uuid:pk>/", PropertyDetailView.as_view(), name="detail"),
    path("favorites/", FavoriteListCreateView.as_view(), name="favorites"),
    path("favorites/<uuid:property_id>/", FavoriteDeleteView.as_view(), name="favorite-delete"),
]
