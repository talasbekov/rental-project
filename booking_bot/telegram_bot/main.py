import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    CallbackContext,
)

from .utils import send_telegram_message
from .. import settings
from .handlers import (
    start_command_handler,
    date_input_handler,
    help_command_handler,
    message_handler,
)

# Enable logging for python-telegram-bot
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создаем отдельный логгер для входящих сообщений
message_logger = logging.getLogger("telegram_messages")


def message_logging_handler(update: Update, context: CallbackContext):
    """Единый логгер для всех входящих сообщений (group=99)."""
    try:
        if not update.message:
            return
            
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else None
        # Определяем тип сообщения и текст для логирования
        if update.message.text:
            message_text = update.message.text
        elif update.message.photo:
            message_text = f"[PHOTO:{len(update.message.photo)} items]"
        else:
            message_text = "[OTHER_CONTENT]"
        
        # Получаем текущий state пользователя
        current_state = "UNKNOWN"
        try:
            from .constants import _get_profile
            profile = _get_profile(chat_id)
            if profile and profile.telegram_state:
                current_state = profile.telegram_state.get("state", "NO_STATE")
        except Exception:
            current_state = "ERROR_GETTING_STATE"
        
        # Логируем входящее сообщение
        message_logger.info(
            f"INCOMING_MESSAGE | chat_id={chat_id} | user_id={user_id} | "
            f"state={current_state} | text='{message_text[:100]}'"
        )
        
    except Exception as e:
        message_logger.error(f"Error in message logging handler: {e}")


async def set_bot_commands(application):
    """Установка команд бота и кнопки меню"""
    commands = [
        ("start", "🏠 Главное меню"),
        ("search", "🔍 Поиск квартир"),
        ("bookings", "📋 Мои бронирования"),
        ("help", "❓ Помощь"),
    ]
    await application.bot.set_my_commands(commands)

    # Установка кнопки меню
    await application.bot.set_chat_menu_button(menu_button={"type": "commands"})


# Global application instance
application = None


def telegram_callback_query_handler(update: Update, context: CallbackContext):
    """Обработка устаревших inline-кнопок.

    Интерфейс бота переведён на обычные кнопки, поэтому при получении
    callback мы просто подсказываем пользователю воспользоваться меню.
    """
    query = update.callback_query
    if not query:
        return

    try:
        query.answer()
    except Exception:  # noqa: BLE001
        logger.warning("Failed to answer callback query")

    chat = query.message.chat if query.message else None
    if chat:
        send_telegram_message(
            chat.id,
            "Интерфейс обновлён. Пожалуйста, используйте кнопки под полем ввода.",
        )


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
            send_telegram_message(
                chat_id, "Пожалуйста, отправьте текст или фотографию."
            )

    except Exception as e:
        logger.error(f"Error in telegram handler: {e}", exc_info=True)
        send_telegram_message(
            update.effective_chat.id, "Произошла ошибка. Попробуйте /start"
        )


def setup_application():
    global application
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN.startswith(
        "PLACEHOLDER"
    ):
        logger.warning("TELEGRAM_BOT_TOKEN not configured; bot will not start.")
        return

    builder = Application.builder().token(settings.TELEGRAM_BOT_TOKEN)
    application = builder.build()

    # ПРАВИЛЬНЫЙ ПОРЯДОК РЕГИСТРАЦИИ: СПЕЦИФИЧНЫЕ → ОБЩИЕ → CATCH-ALL
    
    # 1. СПЕЦИФИЧНЫЕ ХЕНДЛЕРЫ (group=0, по умолчанию)
    # Команды (самые специфичные)
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
            "help", lambda update, ctx: help_command_handler(update.effective_chat.id)
        )
    )

    # Callback query handler для inline кнопок (специфичный)
    application.add_handler(CallbackQueryHandler(telegram_callback_query_handler))
    
    # 2. CATCH-ALL ХЕНДЛЕРЫ (group=90-99, низкий приоритет)
    # Основной обработчик сообщений (catch-all) - group=90
    application.add_handler(
        MessageHandler(filters.TEXT | filters.PHOTO, telegram_message_handler),
        group=90
    )
    
    # Логгер для всех входящих сообщений (мониторинг) - group=99 (самый низкий)
    application.add_handler(
        MessageHandler(filters.TEXT | filters.PHOTO, message_logging_handler),
        group=99
    )

    # Set commands and menu button
    application.job_queue.run_once(lambda ctx: set_bot_commands(application), 0)

    logger.info("Bot initialized")
    return application
