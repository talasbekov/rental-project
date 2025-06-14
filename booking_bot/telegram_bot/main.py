import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from django.conf import settings
from .handlers import (
    start_command_handler,
    search_command_handler,
    search_region_callback_handler,
    search_rooms_callback_handler,
    search_class_callback_handler,
    book_property_callback_handler,
    date_input_handler, # Add date_input_handler
    my_bookings_command_handler, # Added
    cancel_booking_callback_handler # Added
) # Import new handlers

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
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.warning("TELEGRAM_BOT_TOKEN is not configured or is a placeholder. Bot will not be initialized.")
        application = None
        return

    logger.info("Initializing Telegram Bot Application...")
    application_builder = Application.builder().token(settings.TELEGRAM_BOT_TOKEN)

    # Configure persistence if needed (e.g., PicklePersistence)
    # from telegram.ext import PicklePersistence
    # persistence = PicklePersistence(filepath=settings.BASE_DIR / "telegram_bot_persistence.pickle")
    # application_builder.persistence(persistence)

    application = application_builder.build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command_handler))
    application.add_handler(CommandHandler("search", search_command_handler))
    application.add_handler(CallbackQueryHandler(search_region_callback_handler, pattern='^search_region_'))
    application.add_handler(CallbackQueryHandler(search_rooms_callback_handler, pattern='^search_rooms_'))
    application.add_handler(CallbackQueryHandler(search_class_callback_handler, pattern='^search_class_'))
    application.add_handler(CallbackQueryHandler(book_property_callback_handler, pattern='^book_property_'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, date_input_handler))
    application.add_handler(CommandHandler("my_bookings", my_bookings_command_handler))
    application.add_handler(CallbackQueryHandler(cancel_booking_callback_handler, pattern='^cancel_booking_'))
    # Add other handlers (MessageHandler, ConversationHandler, etc.) here as needed

    logger.info("Telegram Bot Application initialized with handlers.")
    return application

# Call setup_application() when Django loads this module,
# or more robustly, in an AppConfig.ready() method.
# For simplicity in this step, we'll rely on it being imported.
# A better way is to use Django's AppConfig.ready() method.

# To run the bot with polling (for development, not for webhook):
# async def main():
#     app = setup_application()
#     if app:
#         logger.info("Starting bot with polling...")
#         await app.initialize() # Initializes application, bot, etc.
#         await app.updater.start_polling() # Starts polling
#         await app.start()
#         # Keep the bot running until interrupted
#         # await app.updater.idle() # This is for older versions or specific run modes
# if __name__ == '__main__':
#     import asyncio
#     asyncio.run(main())
