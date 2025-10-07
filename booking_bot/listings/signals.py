"""Model signal handlers for listings cache invalidation."""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .cache import invalidate_search_cache
from .models import District, Property, PropertyPhoto, PropertyPriceHistory


@receiver([post_save, post_delete], sender=Property)
@receiver([post_save, post_delete], sender=PropertyPhoto)
@receiver([post_save, post_delete], sender=District)
def listings_cache_invalidator(**_: object) -> None:
    """Invalidate cached search results whenever listing data changes."""
    invalidate_search_cache()


@receiver(pre_save, sender=Property)
def store_previous_price(sender, instance, **kwargs):
    """Сохраняем предыдущую цену перед обновлением для истории."""
    if not instance.pk:
        instance._previous_price_per_day = None
        return

    try:
        previous = sender.objects.only("price_per_day").get(pk=instance.pk)
        instance._previous_price_per_day = previous.price_per_day
    except sender.DoesNotExist:  # pragma: no cover - объект удалён одновременно
        instance._previous_price_per_day = None


@receiver(post_save, sender=Property)
def log_price_history(sender, instance, created, **kwargs):
    """Записываем изменение цены в историю для аналитики."""
    previous_price = getattr(instance, "_previous_price_per_day", None)

    price_changed = created or previous_price != instance.price_per_day

    if price_changed:
        PropertyPriceHistory.objects.create(
            property=instance,
            price=instance.price_per_day,
        )

    if hasattr(instance, "_previous_price_per_day"):
        delattr(instance, "_previous_price_per_day")
