from django.db import models
from django.contrib.auth.models import User

class City(models.Model):
    name = models.CharField(max_length=100, unique=True)
    # Add any other city-specific fields if needed in the future

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Cities"

class District(models.Model):
    name = models.CharField(max_length=100)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='districts')
    # Add any other district-specific fields if needed

    def __str__(self):
        return f"{self.name}, {self.city.name}"

    class Meta:
        unique_together = ('name', 'city') # Ensure district names are unique within a city

class Property(models.Model):
    PROPERTY_CLASS_CHOICES = [
        ('comfort', 'Комфорт / Комфорт'), # Adjusted display value slightly
        ('business', 'Business / Бизнес'),
        ('luxury', 'Luxury / Премиум'),
    ]
    # REGION_CHOICES removed, replaced by ForeignKey to District
    STATUS_CHOICES = [
        ('Свободна', 'Available / Свободна'),
        ('Забронирована', 'Booked / Забронирована'),
        ('Занята', 'Occupied / Занята'), # Changed 'maintenance' to 'occupied' for clarity
        ('На обслуживании', 'Maintenance / На обслуживании'), # Added maintenance back as a separate status
    ]
    name = models.CharField(max_length=255)
    description = models.TextField()
    address = models.CharField(max_length=255) # This will be the free-form address
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, related_name='properties') # Link to new District model
    number_of_rooms = models.PositiveIntegerField()
    area = models.DecimalField(max_digits=8, decimal_places=2, help_text="Area in square meters")
    property_class = models.CharField(max_length=20, choices=PROPERTY_CLASS_CHOICES, default='comfort')
    # region field removed
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Свободна')

    # Encrypted fields
    key_safe_code = models.CharField(max_length=50, null=True, blank=True)
    digital_lock_code = models.CharField(max_length=50, null=True, blank=True)

    entry_instructions = models.TextField(null=True, blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='properties', limit_choices_to={'is_staff': True}) # Assuming admins are staff users
    price_per_day = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class PropertyPhoto(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='property_photos/', blank=True, null=True)
    image_url = models.URLField(blank=True, null=True)

    def __str__(self):
        if self.image_url:
            return f"Photo URL for {self.property.name}: {self.image_url}"
        elif self.image:
            return f"Photo file for {self.property.name}: {self.image.name}"
        return f"Empty photo for {self.property.name}"

    def get_photo_url(self):
        """Получить URL фотографии (приоритет - image_url, затем image)"""
        if self.image_url:
            return self.image_url
        elif self.image:
            return self.image.url
        return None

    class Meta:
        ordering = ['id']

# Reviews Section

class Review(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews') # User who wrote the review
    rating = models.PositiveIntegerField(choices=[(i, str(i)) for i in range(1, 6)]) # 1 to 5 stars
    text = models.TextField(blank=True) # Review text can be optional if only rating is given
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Review for {self.property.name} by {self.user.username} - {self.rating} stars"

    class Meta:
        unique_together = ('property', 'user') # Assuming one review per user per property
        ordering = ['-created_at']

class ReviewPhoto(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='photos')
    # Using URLField for now, similar to PropertyPhoto.
    # Could be changed to ImageField if direct uploads are handled by the Django app.
    image_url = models.URLField()
    caption = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Photo for review {self.review.id} by {self.review.user.username}"
