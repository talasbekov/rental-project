from django.db import models
from django.contrib.auth.models import User

class Property(models.Model):
    PROPERTY_CLASS_CHOICES = [
        ('economy', 'Economy'),
        ('business', 'Business'),
        ('luxury', 'Luxury'),
    ]
    REGION_CHOICES = [
        ('yesil', 'Yesil District'),
        ('nurinsky', 'Nurinsky District'),
        ('almaty', 'Almaty District'),
        ('saryarkinsky', 'Saryarkinsky District'),
        ('baikonursky', 'Baikonursky District'),
    ]
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('booked', 'Booked'),
        ('maintenance', 'Maintenance'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField()
    address = models.CharField(max_length=255)
    number_of_rooms = models.PositiveIntegerField()
    area = models.DecimalField(max_digits=8, decimal_places=2, help_text="Area in square meters") # e.g. m²
    property_class = models.CharField(max_length=20, choices=PROPERTY_CLASS_CHOICES, default='economy')
    region = models.CharField(max_length=20, choices=REGION_CHOICES, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    key_safe_code = models.CharField(max_length=50, null=True, blank=True)
    digital_lock_code = models.CharField(max_length=50, null=True, blank=True)
    entry_instructions = models.TextField(null=True, blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='properties', limit_choices_to={'profile__role': 'admin'})
    price_per_day = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class PropertyPhoto(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='photos')
    image_url = models.URLField()
    caption = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Photo for {self.property.name}"
