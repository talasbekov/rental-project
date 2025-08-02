from django.apps import AppConfig

class WhatsAppBotConfig(AppConfig):
    name = 'booking_bot.whatsapp_bot'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        # Ничего не инициализируем здесь — обработка через webhook
        pass