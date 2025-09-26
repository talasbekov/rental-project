import requests
import logging
from django.conf import settings
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from booking_bot.listings import filters
from booking_bot.telegram_bot.admin_handlers import show_admin_panel
from booking_bot.telegram_bot.constants import _get_profile, start_command_handler
from booking_bot.telegram_bot.handlers import (
    help_command_handler,
)
from booking_bot.telegram_bot.state_flow import (
    handle_cancel_booking_start,
    show_user_bookings_with_cancel,
    prompt_city,
)
from booking_bot.telegram_bot.main import telegram_message_handler
from booking_bot.telegram_bot.utils import send_telegram_message

logger = logging.getLogger(__name__)


def setup_bot_menu():
    """Настройка кнопки меню бота рядом со скрепкой"""
    bot_token = settings.TELEGRAM_BOT_TOKEN

    # Установка команд бота
    commands = [
        {"command": "start", "description": "🏠 Главное меню"},
        {"command": "search", "description": "🔍 Поиск квартир"},
        {"command": "bookings", "description": "📋 Мои бронирования"},
        {"command": "status", "description": "📊 Статус текущей брони"},
        {"command": "help", "description": "❓ Помощь"},
        {"command": "admin", "description": "🛠 Панель администратора (для админов)"},
    ]

    # Установка команд
    url = f"https://api.telegram.org/bot{bot_token}/setMyCommands"
    response = requests.post(url, json={"commands": commands})

    if response.status_code == 200:
        logger.info("Bot commands set successfully")
    else:
        logger.error(f"Failed to set bot commands: {response.text}")

    # Установка кнопки меню
    menu_button_url = f"https://api.telegram.org/bot{bot_token}/setChatMenuButton"
    menu_button_data = {"menu_button": {"type": "commands", "text": "Меню"}}

    response = requests.post(menu_button_url, json=menu_button_data)

    if response.status_code == 200:
        logger.info("Bot menu button set successfully")
        return True
    else:
        logger.error(f"Failed to set menu button: {response.text}")
        return False


# Добавить в booking_bot/telegram_bot/main.py
def setup_application():
    global application
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN.startswith(
        "PLACEHOLDER"
    ):
        logger.warning("TELEGRAM_BOT_TOKEN not configured; bot will not start.")
        return

    builder = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN)
    application = builder.build()

    # Обработчики команд
    application.add_handler(
        CommandHandler(
            "start",
            lambda update, ctx: start_command_handler(
                update.effective_chat.id,
                update.effective_user.first_name,
                update.effective_user.last_name,
            ),
        )
    )
    application.add_handler(
        CommandHandler(
            "search",
            lambda update, ctx: prompt_city(
                update.effective_chat.id, _get_profile(update.effective_chat.id)
            ),
        )
    )
    application.add_handler(
        CommandHandler(
            "bookings",
            lambda update, ctx: show_user_bookings_with_cancel(
                update.effective_chat.id, "completed"
            ),
        )
    )
    application.add_handler(
        CommandHandler(
            "status",
            lambda update, ctx: show_user_bookings_with_cancel(
                update.effective_chat.id, "active"
            ),
        )
    )
    application.add_handler(
        CommandHandler(
            "help", lambda update, ctx: help_command_handler(update.effective_chat.id)
        )
    )
    application.add_handler(
        CommandHandler(
            "admin", lambda update, ctx: handle_admin_command(update.effective_chat.id)
        )
    )

    # ПРАВИЛЬНЫЙ ПОРЯДОК РЕГИСТРАЦИИ: СПЕЦИФИЧНЫЕ → ОБЩИЕ → CATCH-ALL
    
    # 1. СПЕЦИФИЧНЫЕ ХЕНДЛЕРЫ (group=0, по умолчанию)
    # Callback query handler для inline кнопок (специфичный)
    from telegram.ext import CallbackQueryHandler
    from .main import telegram_callback_query_handler
    application.add_handler(CallbackQueryHandler(telegram_callback_query_handler))
    
    # Обработчик команд отмены через /cancel_ID (специфичный regex)
    application.add_handler(
        MessageHandler(
            filters.Regex(r"^/cancel_(\d+)$"),
            lambda update, ctx: handle_cancel_command(update, ctx),
        )
    )

    # 2. CATCH-ALL ХЕНДЛЕРЫ (group=90, низкий приоритет)
    # Основной обработчик сообщений (catch-all) - регистрируем в group=90
    application.add_handler(
        MessageHandler(filters.TEXT | filters.PHOTO, telegram_message_handler),
        group=90
    )

    # Настройка меню при запуске
    async def setup_bot_commands(app):
        await app.bot.set_my_commands(
            [
                ("start", "🏠 Главное меню"),
                ("search", "🔍 Поиск квартир"),
                ("bookings", "📋 Мои бронирования"),
                ("status", "📊 Статус текущей брони"),
                ("help", "❓ Помощь"),
                ("admin", "🛠 Админ панель"),
            ]
        )

        # Установка кнопки меню
        await app.bot.set_chat_menu_button(menu_button={"type": "commands"})
        logger.info("Bot commands and menu button set")

    application.job_queue.run_once(lambda ctx: setup_bot_commands(application), 0)

    logger.info("Bot initialized with menu button")
    return application


def handle_admin_command(chat_id):
    """Обработчик команды /admin"""
    profile = _get_profile(chat_id)
    if profile.role in ("admin", "super_admin"):
        show_admin_panel(chat_id)
    else:
        send_telegram_message(
            chat_id, "❌ У вас нет доступа к административной панели."
        )


def handle_cancel_command(update, context):
    """Обработчик команды /cancel_ID"""
    import re

    match = re.match(r"^/cancel_(\d+)$", update.message.text)
    if match:
        booking_id = int(match.group(1))
        handle_cancel_booking_start(update.effective_chat.id, booking_id)
