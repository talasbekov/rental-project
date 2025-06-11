from django.db import models
from django.contrib.auth.models import User

class Property(models.Model):
    PROPERTY_CLASS_CHOICES = [
        ('economy', 'Economy'),
        ('business', 'Business'),
        ('luxury', 'Luxury'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField()
    address = models.CharField(max_length=255)
    number_of_rooms = models.PositiveIntegerField()
    area = models.DecimalField(max_digits=8, decimal_places=2, help_text="Area in square meters") # e.g. m²
    property_class = models.CharField(max_length=20, choices=PROPERTY_CLASS_CHOICES, default='economy')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='properties', limit_choices_to={'profile__role': 'admin'})
    price_per_day = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
