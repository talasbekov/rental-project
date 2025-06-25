import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from .. import settings
from .handlers import (
    start_command_handler,
    callback_query_handler,
    date_input_handler, help_command_handler, message_handler,
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
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN.startswith('PLACEHOLDER'):
        logger.warning("TELEGRAM_BOT_TOKEN not configured; bot will not start.")
        return

    builder = Application.builder().token(settings.TELEGRAM_BOT_TOKEN)
    application = builder.build()

    # Commands
    application.add_handler(CommandHandler('start', start_command_handler))
    application.add_handler(CommandHandler('help', lambda update,ctx: help_command_handler(update.effective_chat.id)))

    # Inline callbacks
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    # Date inputs (strict date format)
    application.add_handler(MessageHandler(filters.Regex(r'^\d{2}\.\d{2}\.\d{4}$') & ~filters.COMMAND,
                                           lambda update,ctx: date_input_handler(update.effective_chat.id, update.message.text)))
    # All other text → message_handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                                           lambda update,ctx: message_handler(update.effective_chat.id, update.message.text)))

    # Set commands
    async def set_cmds(app):
        await app.bot.set_my_commands([('start','Главное меню'),('help','Помощь')])
        logger.info("Commands set")
    application.job_queue.run_once(lambda ctx: set_cmds(application), 0)

    logger.info("Bot initialized")
    return application

