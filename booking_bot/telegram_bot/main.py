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
    """Обработчик inline кнопок (callback_data) с поддержкой FSM states."""
    try:
        query = update.callback_query
        chat_id = query.message.chat.id
        data = query.data
        
        logger.info(f"Received callback data: {data} from chat {chat_id}")
        
        # Подтверждаем получение callback query
        query.answer()
        
        # Получаем текущее состояние пользователя
        from .constants import _get_profile
        profile = _get_profile(chat_id)
        current_state = profile.telegram_state.get("state") if profile.telegram_state else None
        
        # Импортируем необходимые функции
        from .handlers import (
            handle_review_rating_callback,
            handle_submit_review_with_photos,
            show_user_bookings_with_cancel,
            start_command_handler,
            prompt_city
        )
        
        # ГЛОБАЛЬНЫЕ inline кнопки (работают из любого состояния)
        if data == "main_menu":
            # Возврат в главное меню
            start_command_handler(chat_id)
            return
            
        elif data == "cancel":
            # Отмена/возврат в главное меню
            start_command_handler(chat_id)
            return
            
        elif data == "main_current":
            # Возврат к текущим бронированиям
            show_user_bookings_with_cancel(chat_id, "active")
            return
            
        elif data == "search_apartments":
            # Начать поиск квартир
            prompt_city(chat_id, profile)
            return
        
        # STATE-ЗАВИСИМЫЕ inline кнопки
        # Обработка рейтинга отзывов (работает в любом состоянии)
        if data and len(data.split("_")) == 3 and data.split("_")[0] == "review":
            parts = data.split("_")
            try:
                booking_id = int(parts[1])
                rating = int(parts[2])
                if 1 <= rating <= 5:  # Валидация рейтинга
                    handle_review_rating_callback(chat_id, booking_id, rating)
                else:
                    logger.warning(f"Invalid rating value: {rating}")
            except (ValueError, IndexError) as e:
                logger.warning(f"Invalid review callback format: {data}, error: {e}")
            return
        
        # Завершение загрузки фото для отзыва
        elif data == "submit_review_with_photos":
            handle_submit_review_with_photos(chat_id)
            return
        
        # НАВИГАЦИЯ ПО РЕЗУЛЬТАТАМ ПОИСКА
        elif data.startswith("nav_"):
            from .handlers import navigate_results
            # Форматы: nav_prev, nav_next, nav_page_<num>
            if data == "nav_prev":
                navigate_results(chat_id, profile, "◀️ Назад")
            elif data == "nav_next":  
                navigate_results(chat_id, profile, "Вперёд ▶️")
            elif data.startswith("nav_page_"):
                page_num = data.split("_")[-1]
                navigate_results(chat_id, profile, f"Страница {page_num}")
            return
            
        # УПРАВЛЕНИЕ БРОНИРОВАНИЯМИ
        elif data.startswith("booking_"):
            # Форматы: booking_view_<id>, booking_cancel_<id>, booking_extend_<id>
            parts = data.split("_")
            if len(parts) >= 3:
                action = parts[1]
                booking_id = parts[2]
                if action == "view":
                    from .handlers import show_booking_details
                    show_booking_details(chat_id, int(booking_id))
                elif action == "cancel":
                    from .handlers import handle_cancel_booking_start
                    handle_cancel_booking_start(chat_id, int(booking_id))
                elif action == "extend":
                    from .handlers import handle_extend_booking_start  
                    handle_extend_booking_start(chat_id, int(booking_id))
            return
            
        # УПРАВЛЕНИЕ КВАРТИРАМИ (для админов)
        elif data.startswith("property_"):
            # Форматы: property_view_<id>, property_edit_<id>, property_delete_<id>
            parts = data.split("_")
            if len(parts) >= 3:
                action = parts[1]
                property_id = parts[2]
                if action == "view":
                    from .handlers import show_property_details
                    show_property_details(chat_id, int(property_id))
                elif action == "edit":
                    from .admin_handlers import show_edit_property_menu
                    show_edit_property_menu(chat_id, int(property_id))
                elif action == "delete":
                    from .admin_handlers import confirm_property_deletion
                    confirm_property_deletion(chat_id, int(property_id))
            return
        
        # Неизвестная inline кнопка
        else:
            logger.warning(f"Unknown callback data: {data} from state: {current_state}")
            query.answer("Неизвестная команда")
            
    except Exception as e:
        logger.error(f"Error in callback query handler: {e}", exc_info=True)
        if update.callback_query:
            update.callback_query.answer("Произошла ошибка")
        

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
