"""Models for the review domain.

Defines the ``Review`` entity representing feedback and ratings
submitted by guests for properties they have stayed at. Each review
includes a numerical rating, an optional comment and timestamps.
One user can leave at most one review per property per booking.
"""

from __future__ import annotations

import builtins

from django.core.validators import MaxValueValidator, MinValueValidator  # type: ignore
from django.db import models  # type: ignore
from django.utils.translation import gettext_lazy as _  # type: ignore


class Review(models.Model):
    """Represents a review left by a guest for a property."""

    user = models.ForeignKey(
        'users.CustomUser', on_delete=models.CASCADE, related_name='reviews'
    )
    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE, related_name='reviews'
    )
    booking = models.OneToOneField(
        'bookings.Booking',
        on_delete=models.CASCADE,
        related_name='review',
        null=True,
        blank=True,
        help_text=_('Бронирование, к которому относится отзыв')
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='Оценка от 1 до 5'
    )
    comment = models.TextField(blank=True)

    # Дополнительные категории оценок (опционально)
    cleanliness_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_('Чистота')
    )
    location_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_('Расположение')
    )
    value_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_('Соотношение цена/качество')
    )
    communication_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_('Качество связи с владельцем')
    )
    accuracy_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_('Соответствие описанию')
    )
    check_in_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_('Процесс заселения')
    )

    # Ответ риелтора
    realtor_response = models.TextField(
        blank=True,
        help_text=_('Ответ владельца на отзыв')
    )
    realtor_response_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Дата ответа владельца')
    )

    # Модерация
    is_approved = models.BooleanField(
        default=True,
        help_text=_('Одобрен модератором')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'property', 'booking')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['property', '-created_at']),
            models.Index(fields=['user']),
            models.Index(fields=['rating']),
        ]

    def __str__(self) -> str:
        return f"Review by {self.user_id} for property {self.property_id} (Rating: {self.rating})"

    @builtins.property
    def average_rating(self) -> float:
        """Средняя оценка по всем категориям."""
        ratings = [
            self.rating,
            self.cleanliness_rating,
            self.location_rating,
            self.value_rating,
            self.communication_rating,
            self.accuracy_rating,
            self.check_in_rating,
        ]
        valid_ratings = [r for r in ratings if r is not None]
        return sum(valid_ratings) / len(valid_ratings) if valid_ratings else self.rating


class ReviewPhoto(models.Model):
    """
    Фотографии, прикреплённые к отзыву.

    Гости могут добавить до 5 фотографий к своему отзыву,
    чтобы подкрепить свои впечатления визуально.
    """

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name='photos',
        help_text=_('Отзыв, к которому относится фото')
    )
    image = models.ImageField(
        upload_to='reviews/photos/%Y/%m/%d/',
        help_text=_('Фотография')
    )
    caption = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Подпись к фото')
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text=_('Порядок отображения')
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Фотография отзыва')
        verbose_name_plural = _('Фотографии отзывов')
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['review', 'order']),
        ]

    def __str__(self) -> str:
        return f"Photo for review {self.review_id} (order {self.order})" 
