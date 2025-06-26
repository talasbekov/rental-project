import django_filters
from .models import Property

class PropertyFilter(django_filters.FilterSet):
    area_min = django_filters.NumberFilter(field_name="area", lookup_expr='gte')
    area_max = django_filters.NumberFilter(field_name="area", lookup_expr='lte')
    # For CharFields with choices, 'exact' is usually appropriate.
    # The field name in 'fields' will automatically create a filter for it.
    # If more control is needed (e.g. lookup_expr), define them explicitly like area_min/max.

    class Meta:
        model = Property
        # Define fields and their default lookup_expr if not 'exact'
        # For choice fields, 'exact' is the default and usually what's needed.
        fields = {
            'district': ['exact'], # Filter by district ID
            'number_of_rooms': ['exact'],
            'property_class': ['exact'], # Filter by class key e.g. 'economy'
            'status': ['exact'], # Filter by status key e.g. 'Свободна'
            'price_per_day': ['gte', 'lte'],
            # area is handled by area_min, area_max above
        }

# Example of explicit definition if needed:
# class PropertyFilter(django_filters.FilterSet):
#     region = django_filters.ChoiceFilter(choices=Property.REGION_CHOICES)
#     property_class = django_filters.ChoiceFilter(choices=Property.PROPERTY_CLASS_CHOICES)
#     status = django_filters.ChoiceFilter(choices=Property.STATUS_CHOICES)
#     number_of_rooms = django_filters.NumberFilter()
#     price_per_day_min = django_filters.NumberFilter(field_name="price_per_day", lookup_expr='gte')
#     price_per_day_max = django_filters.NumberFilter(field_name="price_per_day", lookup_expr='lte')
#     area_min = django_filters.NumberFilter(field_name="area", lookup_expr='gte')
#     area_max = django_filters.NumberFilter(field_name="area", lookup_expr='lte')

#     class Meta:
#         model = Property
#         fields = [ # Simpler list format when not specifying lookup expressions in Meta
#             'region', 'property_class', 'status', 'number_of_rooms',
#             'price_per_day_min', 'price_per_day_max', 'area_min', 'area_max'
#         ]

# Sticking to the simpler Meta definition for now as it's less verbose and DRF/django-filter handles defaults well.
# The provided code snippet in the prompt uses a dictionary for fields, which is also fine.
# The key is to ensure 'region' and 'status' are included and use appropriate lookups.
# Using ['exact'] for choice fields is generally correct.
