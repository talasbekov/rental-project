import django_filters
from .models import Property

class PropertyFilter(django_filters.FilterSet):
    area_min = django_filters.NumberFilter(field_name="area", lookup_expr='gte')
    area_max = django_filters.NumberFilter(field_name="area", lookup_expr='lte')
    # number_of_rooms, property_class can be filtered directly by name

    class Meta:
        model = Property
        fields = {
            'number_of_rooms': ['exact'],
            'property_class': ['exact'],
            # area is handled by area_min, area_max
            'price_per_day': ['gte', 'lte'], # Allow price range filtering too
        }
