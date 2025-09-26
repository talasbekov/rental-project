from django.apps import AppConfig


class ListingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "booking_bot.listings"

    def ready(self) -> None:  # pragma: no cover - import side effects
        try:
            from . import signals  # noqa: F401
        except Exception:
            # Fallback to avoid breaking startup if signals fail to import during migrations
            pass
