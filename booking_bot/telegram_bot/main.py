import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from .. import settings
from .handlers import (
    start_command_handler,
    callback_query_handler,
    date_input_handler,
)

# Enable logging for python-telegram-bot
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global application instance
application = None

def setup_application():
    global application
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN == "7302267102:AAGZL04EhwnZDYInhmPtS_LU_3wS0vecotM":
        logger.warning("TELEGRAM_BOT_TOKEN is not configured or is a placeholder. Bot will not be initialized.")
        application = None
        return

    logger.info("Initializing Telegram Bot Application...")
    application_builder = Application.builder().token(settings.TELEGRAM_BOT_TOKEN)

    application = application_builder.build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command_handler))

    # Add the central callback handler
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    # MessageHandler for date input during booking flow (text_message_handler was removed from handlers.py)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, date_input_handler))

    # application.add_handler(CommandHandler("my_bookings", my_bookings_command_handler)) # Deprecated
    # Add other handlers (MessageHandler, ConversationHandler, etc.) here as needed

    # Set bot commands for the menu button
    # We run this asynchronously to avoid blocking the setup
    async def set_commands(app):
        await app.bot.set_my_commands([
            ("start", "Главное меню"),
        ])
        logger.info("Bot commands set for the menu button.")

    application.job_queue.run_once(lambda _: set_commands(application), 0)


    logger.info("Telegram Bot Application initialized with handlers.")
    return application

