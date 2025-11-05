from __future__ import annotations

from django.core.management.base import BaseCommand  # type: ignore

from apps.telegrambot.bot import run_bot


class Command(BaseCommand):
    help = "Запускает Telegram-бот ЖильеGO"

    def handle(self, *args, **options):  # type: ignore
        run_bot()
