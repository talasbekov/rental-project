"""Model definition for favorites.

The ``Favorite`` model represents a bookmark created by a guest for a
particular property. Users can add and remove favorites to keep
track of properties they like. Duplicate favorites are prevented via
a unique constraint.
"""

from __future__ import annotations

from django.db import models  # type: ignore


class Favorite(models.Model):
    """A user's favorite property."""

    user = models.ForeignKey(
        'users.CustomUser', on_delete=models.CASCADE, related_name='favorites'
    )
    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE, related_name='favorited_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'property')
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"Favorite property {self.property_id} by user {self.user_id}"