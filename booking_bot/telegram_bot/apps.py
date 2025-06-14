from django.apps import AppConfig
import logging
import asyncio

logger = logging.getLogger(__name__)

class TelegramBotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'booking_bot.telegram_bot' # Corrected name

    # Store bot application and related asyncio task
    bot_application = None
    bot_task = None # For webhook's internal update processing if needed

    async def _initialize_bot(self):
        # This is the async part of the initialization
        from .main import setup_application # Import here to avoid circular deps

        TelegramBotConfig.bot_application = setup_application()
        if TelegramBotConfig.bot_application:
            await TelegramBotConfig.bot_application.initialize() # Important for Webhook setup

            # If using PTB's built-in webserver (not recommended with Django)
            # await TelegramBotConfig.bot_application.updater.start_webhook(listen="0.0.0.0", port=8000, url_path=settings.TELEGRAM_WEBHOOK_PATH)
            # await TelegramBotConfig.bot_application.start()

            # When using Django to handle the webhook endpoint, PTB's Application
            # just needs to be initialized. The incoming updates will be fed to it manually.
            logger.info("Telegram bot application initialized via AppConfig.")
        else:
            logger.warning("Telegram bot application could not be initialized (likely missing token).")


    def ready(self):
        # This method is called once Django is ready
        logger.info("TelegramBotConfig ready method called.")
        # Avoid running this in manage.py subcommands like makemigrations
        import sys
        if 'runserver' in sys.argv or 'gunicorn' in sys.argv: # Or any other server command
            # Run the async initialization in a way that doesn't block Django's startup
            # For Django 3.1+ and Python 3.7+
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If event loop is already running (e.g. in Jupyter or other async environments)
                    # This might need careful handling depending on the environment.
                    # For now, we assume it's not running or we can schedule on it.
                     asyncio.ensure_future(self._initialize_bot())
                else:
                    asyncio.run(self._initialize_bot())
            except RuntimeError as e: # Handle cases where event loop is already running or cannot be obtained
                logger.error(f"Could not initialize Telegram bot due to asyncio event loop issue: {e}. Manual setup might be required.")
                # Fallback or alternative setup might be needed here depending on deployment.
                # For simpler cases or where an outer async context is managing Django,
                # just calling self._initialize_bot() might be fine if it's already awaited.
        else:
            logger.info("Skipping Telegram bot initialization (not a server command).")
