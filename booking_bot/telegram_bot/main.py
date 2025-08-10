import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, CallbackContext

from .utils import send_telegram_message
from .. import settings
from .handlers import (
    start_command_handler,
    date_input_handler, help_command_handler, message_handler,
)

# Enable logging for python-telegram-bot
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def set_bot_commands(application):
    """Установка команд бота и кнопки меню"""
    commands = [
        ('start', '🏠 Главное меню'),
        ('search', '🔍 Поиск квартир'),
        ('bookings', '📋 Мои бронирования'),
        ('help', '❓ Помощь')
    ]
    await application.bot.set_my_commands(commands)

    # Установка кнопки меню
    await application.bot.set_chat_menu_button(
        menu_button={
            "type": "commands"
        }
    )

# Global application instance
application = None

def telegram_message_handler(update: Update, context: CallbackContext):
    """Основной обработчик телеграм сообщений."""
    try:
        chat_id = update.effective_chat.id

        # Обработка текстовых сообщений
        if update.message and update.message.text:
            text = update.message.text
            message_handler(chat_id, text, update, context)

        # Обработка фотографий
        elif update.message and update.message.photo:
            # Для фото передаем пустой текст, но передаем update и context
            message_handler(chat_id, "", update, context)

        else:
            send_telegram_message(chat_id, "Пожалуйста, отправьте текст или фотографию.")

    except Exception as e:
        logger.error(f"Error in telegram handler: {e}", exc_info=True)
        send_telegram_message(update.effective_chat.id, "Произошла ошибка. Попробуйте /start")

def setup_application():
    global application
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN.startswith('PLACEHOLDER'):
        logger.warning("TELEGRAM_BOT_TOKEN not configured; bot will not start.")
        return

    builder = Application.builder().token(settings.TELEGRAM_BOT_TOKEN)
    application = builder.build()

    # Commands
    application.add_handler(CommandHandler('start', lambda update, ctx: start_command_handler(
        update.effective_chat.id,
        update.effective_user.first_name,
        update.effective_user.last_name
    )))
    application.add_handler(CommandHandler('help', lambda update,ctx: help_command_handler(update.effective_chat.id)))

    # УБИРАЕМ дублирующиеся обработчики и оставляем только один основной
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, telegram_message_handler))

    # Set commands and menu button
    application.job_queue.run_once(lambda ctx: set_bot_commands(application), 0)

    logger.info("Bot initialized")
    return application