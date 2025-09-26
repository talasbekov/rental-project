"""Model signal handlers for listings cache invalidation."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_search_cache
from .models import District, Property, PropertyPhoto


@receiver([post_save, post_delete], sender=Property)
@receiver([post_save, post_delete], sender=PropertyPhoto)
@receiver([post_save, post_delete], sender=District)
def listings_cache_invalidator(**_: object) -> None:
    """Invalidate cached search results whenever listing data changes."""
    invalidate_search_cache()
