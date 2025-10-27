"""Property domain models for ЖильеGO."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Amenity(models.Model):
    """Catalog of property amenities."""

    class Category(models.TextChoices):
        BASIC = "basic", "Основные"
        EXTRA = "extra", "Дополнительные"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.BASIC)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class Property(models.Model):
    """Property inventory item available for booking."""

    class PropertyType(models.TextChoices):
        APARTMENT = "apartment", "Квартира"
        HOUSE = "house", "Дом"
        COTTAGE = "cottage", "Коттедж"
        ROOM = "room", "Комната"
        HOSTEL = "hostel", "Хостел"

    class PropertyClass(models.TextChoices):
        COMFORT = "comfort", "Комфорт"
        BUSINESS = "business", "Бизнес"
        PREMIUM = "premium", "Премиум"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PENDING = "pending", "На модерации"
        ACTIVE = "active", "Активен"
        INACTIVE = "inactive", "Неактивен"
        BLOCKED = "blocked", "Заблокирован"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="properties",
    )
    title = models.CharField(max_length=200)
    description = models.TextField()

    city = models.CharField(max_length=120)
    district = models.CharField(max_length=120, blank=True)
    address_line = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    property_type = models.CharField(max_length=20, choices=PropertyType.choices)
    property_class = models.CharField(max_length=20, choices=PropertyClass.choices, default=PropertyClass.COMFORT)

    rooms = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    sleeps = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    area = models.PositiveIntegerField(help_text="Площадь в квадратных метрах")
    floor = models.PositiveSmallIntegerField(null=True, blank=True)
    total_floors = models.PositiveSmallIntegerField(null=True, blank=True)

    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    min_stay_nights = models.PositiveSmallIntegerField(default=1)
    max_stay_nights = models.PositiveSmallIntegerField(null=True, blank=True)

    check_in_from = models.TimeField()
    check_in_to = models.TimeField()
    check_out_from = models.TimeField()
    check_out_to = models.TimeField()

    cancellation_policy = models.CharField(max_length=20, default="moderate")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    amenities = models.ManyToManyField(Amenity, related_name="properties", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("city", "district")),
            models.Index(fields=("status",)),
            models.Index(fields=("base_price",)),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.title


class PropertyPhoto(models.Model):
    """Property photos with ordering."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="properties/")
    is_primary = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("order", "uploaded_at")
        constraints = [
            models.UniqueConstraint(
                fields=("property", "order"),
                name="unique_property_photo_order",
            )
        ]

    def save(self, *args, **kwargs):
        if self.is_primary:
            PropertyPhoto.objects.filter(property=self.property, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)

    def __str__(self) -> str:  # pragma: no cover

        return f"{self.property_id} photo {self.order}"


class Favorite(models.Model):
    """User favorites linking properties."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "property")
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user_id} fav {self.property_id}"
