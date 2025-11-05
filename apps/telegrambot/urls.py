"""URL routing for Telegram bot webhook."""

from django.urls import path

from .views import telegram_webhook, telegram_health

app_name = 'telegrambot'

urlpatterns = [
    path('webhook/', telegram_webhook, name='webhook'),
    path('health/', telegram_health, name='health'),
]
