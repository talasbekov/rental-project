# booking_bot/whatsapp_bot/management/commands/setup_whatsapp_webhook.py

import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from django.urls import reverse


class Command(BaseCommand):
    help = 'Настройка webhook для WhatsApp Business API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--domain',
            type=str,
            help='Домен для webhook (например, https://example.com)',
            required=True
        )

    def handle(self, *args, **options):
        domain = options['domain'].rstrip('/')

        # Формируем URL webhook
        webhook_url = f"{domain}/whatsapp/webhook/"

        # URL для настройки webhook
        api_url = f"https://graph.facebook.com/v18.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/subscribed_apps"

        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        # Подписываемся на приложение
        response = requests.post(api_url, headers=headers)

        if response.status_code == 200:
            self.stdout.write(
                self.style.SUCCESS(f'Успешно настроен webhook для {webhook_url}')
            )

            # Выводим информацию для настройки в Facebook Developer Console
            self.stdout.write(
                self.style.WARNING(
                    f"\nТеперь настройте webhook в Facebook Developer Console:\n"
                    f"1. Откройте https://developers.facebook.com/apps/{settings.WHATSAPP_BUSINESS_ACCOUNT_ID}/whatsapp/settings/\n"
                    f"2. В разделе 'Webhook' нажмите 'Edit'\n"
                    f"3. Callback URL: {webhook_url}\n"
                    f"4. Verify Token: {settings.WHATSAPP_VERIFY_TOKEN}\n"
                    f"5. Подпишитесь на webhook fields: messages, messaging_postbacks\n"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f'Ошибка настройки webhook: {response.status_code} - {response.text}'
                )
            )
