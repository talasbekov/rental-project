from django.core.management.base import BaseCommand
from booking_bot.telegram_bot.bot_setup import setup_bot_menu


class Command(BaseCommand):
    help = "Настройка меню Telegram бота"

    def handle(self, *args, **options):
        if setup_bot_menu():
            self.stdout.write(self.style.SUCCESS("✅ Меню бота успешно настроено!"))
            self.stdout.write(
                "Теперь пользователи могут:\n"
                "1. Открыть меню через кнопку рядом со скрепкой\n"
                "2. Использовать команды через /\n"
                "3. Видеть подсказки при вводе /"
            )
        else:
            self.stdout.write(self.style.ERROR("❌ Ошибка при настройке меню бота"))
