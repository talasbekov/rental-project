from rest_framework import viewsets, filters as drf_filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Property
from .serializers import PropertySerializer
from .filters import PropertyFilter # Import the custom filter
from rest_framework.permissions import IsAuthenticatedOrReadOnly # Allow public read

class PropertyViewSet(viewsets.ModelViewSet):
    queryset = Property.objects.all()
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticatedOrReadOnly] # Allow anyone to view, but only auth users to change
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_class = PropertyFilter
    search_fields = ['name', 'address', 'description']
    ordering_fields = ['price_per_day', 'created_at', 'area', 'number_of_rooms']
    ordering = ['-created_at']
