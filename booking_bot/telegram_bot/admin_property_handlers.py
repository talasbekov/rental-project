import logging
import requests
from telegram import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup

from booking_bot.users.models import UserProfile
from booking_bot.core.models import AuditLog
from .constants import (
    _get_profile, log_handler, STATE_ADMIN_MENU
)
from .utils import send_telegram_message
from ..settings import API_BASE

logger = logging.getLogger(__name__)

# Admin states for property management
STATE_ADMIN_PROPERTY_LIST = "admin_property_list"
STATE_ADMIN_PROPERTY_DETAIL = "admin_property_detail" 
STATE_ADMIN_PROPERTY_EDIT = "admin_property_edit"
STATE_ADMIN_BOOKINGS_LIST = "admin_bookings_list"
STATE_ADMIN_REVIEWS_LIST = "admin_reviews_list"
STATE_ADMIN_DASHBOARD = "admin_dashboard"

# Property editing states
STATE_EDIT_PROPERTY_NAME = "edit_property_name"
STATE_EDIT_PROPERTY_DESCRIPTION = "edit_property_description"
STATE_EDIT_PROPERTY_PRICE = "edit_property_price"
STATE_EDIT_PROPERTY_STATUS = "edit_property_status"
STATE_EDIT_ACCESS_CODES = "edit_access_codes"
STATE_EDIT_ENTRY_CODE = "edit_entry_code"
STATE_EDIT_KEY_SAFE_CODE = "edit_key_safe_code"
STATE_EDIT_DIGITAL_LOCK_CODE = "edit_digital_lock_code"


def check_admin_access(profile: UserProfile) -> bool:
    """Check if user has admin access"""
    return profile and profile.role in ('admin', 'super_admin')


def get_auth_headers(profile: UserProfile) -> dict:
    """Get authentication headers for API requests"""
    state_data = profile.telegram_state or {}
    token = state_data.get('jwt_access_token')
    return {'Authorization': f'Bearer {token}'} if token else {}


@log_handler
def handle_admin_menu(chat_id: int, text: str = None) -> bool:
    """Main admin menu handler"""
    profile = _get_profile(chat_id)
    
    if not check_admin_access(profile):
        send_telegram_message(chat_id, "❌ У вас нет доступа к админ-панели.")
        return False
    
    # Set admin state
    state_data = profile.telegram_state or {}
    state_data['state'] = STATE_ADMIN_MENU
    profile.telegram_state = state_data
    profile.save()
    
    keyboard = [
        [KeyboardButton("🏠 Мои квартиры"), KeyboardButton("📊 Дашборд")],
        [KeyboardButton("📋 Бронирования"), KeyboardButton("⭐ Отзывы")],
        [KeyboardButton("➕ Добавить квартиру")],
        [KeyboardButton("👤 Пользовательское меню")]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    role_text = "Супер-администратор" if profile.role == 'super_admin' else "Администратор"
    
    send_telegram_message(
        chat_id,
        f"🔧 *Админ-панель*\n"
        f"Роль: {role_text}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup.to_dict()
    )
    
    return True


@log_handler 
def handle_property_list(chat_id: int, text: str = None) -> bool:
    """Show list of properties for admin"""
    profile = _get_profile(chat_id)
    
    if not check_admin_access(profile):
        return False
    
    try:
        headers = get_auth_headers(profile)
        url = f"{API_BASE}/properties/my_properties/"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            properties = response.json()
            
            if not properties:
                send_telegram_message(
                    chat_id,
                    "📭 *У вас пока нет квартир*\n\n"
                    "Нажмите «➕ Добавить квартиру» для создания первой квартиры."
                )
                return True
            
            # Create inline keyboard for properties
            keyboard = []
            for prop in properties[:10]:  # Limit to 10 for readability
                status_emoji = {
                    'Свободна': '✅',
                    'Забронирована': '📅', 
                    'Занята': '🔒',
                    'На обслуживании': '🔧'
                }.get(prop['status'], '❓')
                
                button_text = f"{status_emoji} {prop['name'][:25]}"
                if len(prop['name']) > 25:
                    button_text += "..."
                    
                keyboard.append([
                    InlineKeyboardButton(
                        button_text,
                        callback_data=f"admin_property_detail_{prop['id']}"
                    )
                ])
            
            # Add navigation buttons
            keyboard.append([
                InlineKeyboardButton("🔄 Обновить", callback_data="admin_property_refresh"),
                InlineKeyboardButton("📊 Статистика", callback_data="admin_dashboard")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            total_count = len(properties)
            send_telegram_message(
                chat_id,
                f"🏠 *Мои квартиры* ({total_count})\n\n"
                f"Выберите квартиру для просмотра:",
                reply_markup=reply_markup.to_dict()
            )
            
            # Update state
            state_data = profile.telegram_state or {}
            state_data['state'] = STATE_ADMIN_PROPERTY_LIST
            profile.telegram_state = state_data
            profile.save()
            
        else:
            send_telegram_message(chat_id, "❌ Ошибка получения списка квартир")
            
    except Exception as e:
        logger.error(f"Error getting property list: {e}")
        send_telegram_message(chat_id, "❌ Произошла ошибка")
    
    return True


@log_handler
def handle_property_detail(chat_id: int, property_id: int) -> bool:
    """Show property details with admin actions"""
    profile = _get_profile(chat_id)
    
    if not check_admin_access(profile):
        return False
    
    try:
        headers = get_auth_headers(profile)
        url = f"{API_BASE}/properties/{property_id}/"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            prop = response.json()
            
            # Format property details
            rating_display = prop.get('rating_display', 'Нет отзывов')
            
            details = (
                f"🏠 *{prop['name']}*\n\n"
                f"📍 Адрес: {prop['address']}\n"
                f"🏘️ Район: {prop.get('district', {}).get('name', 'Не указан')}\n"
                f"🛏️ Комнат: {prop['number_of_rooms']}\n"
                f"📐 Площадь: {prop['area']} м²\n"
                f"⭐ Рейтинг: {rating_display}\n"
                f"💰 Цена: {prop['price_per_day']} ₸/сутки\n"
                f"📊 Статус: {prop['status']}\n\n"
                f"📝 Описание:\n{prop['description'][:200]}"
            )
            
            if len(prop['description']) > 200:
                details += "..."
            
            # Show access codes if user has permission
            if prop.get('entry_code_display'):
                details += f"\n\n🔐 *Коды доступа:*\n"
                if prop['entry_code_display']:
                    details += f"🏠 Домофон: `{prop['entry_code_display']}`\n"
                if prop.get('key_safe_code_display'):
                    details += f"🗝️ Сейф: `{prop['key_safe_code_display']}`\n"  
                if prop.get('digital_lock_code_display'):
                    details += f"🔑 Замок: `{prop['digital_lock_code_display']}`\n"
            
            # Create action buttons
            keyboard = [
                [
                    InlineKeyboardButton("✏️ Редактировать", callback_data=f"admin_edit_property_{property_id}"),
                    InlineKeyboardButton("📋 Бронирования", callback_data=f"admin_bookings_{property_id}")
                ],
                [
                    InlineKeyboardButton("⭐ Отзывы", callback_data=f"admin_reviews_{property_id}"),
                    InlineKeyboardButton("📊 Статистика", callback_data=f"admin_stats_{property_id}")
                ],
                [
                    InlineKeyboardButton("🔒 Коды доступа", callback_data=f"admin_codes_{property_id}")
                ],
                [
                    InlineKeyboardButton("« Назад к списку", callback_data="admin_property_list")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            send_telegram_message(
                chat_id,
                details,
                reply_markup=reply_markup.to_dict()
            )
            
            # Update state
            state_data = profile.telegram_state or {}
            state_data['state'] = STATE_ADMIN_PROPERTY_DETAIL
            state_data['current_property_id'] = property_id
            profile.telegram_state = state_data
            profile.save()
            
            # Log access
            AuditLog.objects.create(
                user=profile.user,
                action='view_property_details',
                resource_type='Property',
                resource_id=property_id,
                details={'property_name': prop['name']}
            )
            
        else:
            send_telegram_message(chat_id, "❌ Квартира не найдена или нет доступа")
            
    except Exception as e:
        logger.error(f"Error getting property details: {e}")
        send_telegram_message(chat_id, "❌ Произошла ошибка")
    
    return True


@log_handler 
def handle_property_bookings(chat_id: int, property_id: int) -> bool:
    """Show bookings for a property"""
    profile = _get_profile(chat_id)
    
    if not check_admin_access(profile):
        return False
    
    try:
        headers = get_auth_headers(profile)
        url = f"{API_BASE}/properties/{property_id}/bookings/"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            bookings = response.json()
            
            if not bookings:
                send_telegram_message(
                    chat_id,
                    "📭 *Бронирований не найдено*\n\n"
                    "У этой квартиры пока нет бронирований."
                )
                return True
            
            # Format bookings list
            text = f"📋 *Бронирования квартиры*\n\n"
            
            # Group by status
            active_bookings = [b for b in bookings if b['status'] in ['confirmed', 'pending_payment']]
            completed_bookings = [b for b in bookings if b['status'] == 'completed']
            cancelled_bookings = [b for b in bookings if b['status'] == 'cancelled']
            
            if active_bookings:
                text += "🔥 *Активные:*\n"
                for booking in active_bookings[:5]:
                    status_emoji = "✅" if booking['status'] == 'confirmed' else "⏳"
                    text += (
                        f"{status_emoji} {booking['guest_name']} | "
                        f"{booking['start_date']} - {booking['end_date']} | "
                        f"{booking['total_price']}₸\n"
                    )
                text += "\n"
            
            if completed_bookings:
                text += f"✅ *Завершенные:* {len(completed_bookings)}\n"
                
            if cancelled_bookings:
                text += f"❌ *Отмененные:* {len(cancelled_bookings)}\n"
            
            # Create action buttons
            keyboard = [
                [
                    InlineKeyboardButton("📊 Подробная статистика", 
                                       callback_data=f"admin_booking_stats_{property_id}"),
                ],
                [
                    InlineKeyboardButton("« Назад к квартире", 
                                       callback_data=f"admin_property_detail_{property_id}")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            send_telegram_message(
                chat_id,
                text,
                reply_markup=reply_markup.to_dict()
            )
            
        else:
            send_telegram_message(chat_id, "❌ Ошибка получения бронирований")
            
    except Exception as e:
        logger.error(f"Error getting property bookings: {e}")
        send_telegram_message(chat_id, "❌ Произошла ошибка")
    
    return True


@log_handler
def handle_property_reviews(chat_id: int, property_id: int) -> bool:
    """Show reviews for a property"""
    profile = _get_profile(chat_id)
    
    if not check_admin_access(profile):
        return False
    
    try:
        headers = get_auth_headers(profile)
        url = f"{API_BASE}/properties/{property_id}/reviews/"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            reviews = response.json()
            
            if not reviews:
                send_telegram_message(
                    chat_id,
                    "📭 *Отзывов не найдено*\n\n"
                    "У этой квартиры пока нет отзывов."
                )
                return True
            
            # Format reviews
            text = f"⭐ *Отзывы о квартире*\n\n"
            
            for review in reviews[:5]:  # Show first 5 reviews
                stars = "⭐" * review['rating']
                text += (
                    f"{stars} *{review['user_name']}*\n"
                    f"_{review['created_at'][:10]}_\n"
                )
                
                if review['comment']:
                    comment = review['comment'][:100]
                    if len(review['comment']) > 100:
                        comment += "..."
                    text += f"{comment}\n"
                
                text += "\n"
            
            if len(reviews) > 5:
                text += f"... и еще {len(reviews) - 5} отзывов"
            
            # Create action buttons
            keyboard = [
                [
                    InlineKeyboardButton("« Назад к квартире", 
                                       callback_data=f"admin_property_detail_{property_id}")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            send_telegram_message(
                chat_id,
                text,
                reply_markup=reply_markup.to_dict()
            )
            
        else:
            send_telegram_message(chat_id, "❌ Ошибка получения отзывов")
            
    except Exception as e:
        logger.error(f"Error getting property reviews: {e}")
        send_telegram_message(chat_id, "❌ Произошла ошибка")
    
    return True


@log_handler
def handle_admin_dashboard(chat_id: int) -> bool:
    """Show admin dashboard with statistics"""
    profile = _get_profile(chat_id)
    
    if not check_admin_access(profile):
        return False
    
    try:
        headers = get_auth_headers(profile)
        url = f"{API_BASE}/properties/dashboard/"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            stats = response.json()
            
            text = (
                f"📊 *Панель управления*\n\n"
                f"🏠 Квартир: {stats['total_properties']}\n"
                f"📋 Активных бронирований: {stats['active_bookings']}\n"
                f"✅ Завершенных бронирований: {stats['completed_bookings']}\n"
                f"⭐ Всего отзывов: {stats['total_reviews']}\n"
                f"🌟 Средний рейтинг: {stats['average_rating']}\n\n"
            )
            
            # Add quick actions
            keyboard = [
                [
                    InlineKeyboardButton("🏠 Мои квартиры", callback_data="admin_property_list"),
                    InlineKeyboardButton("➕ Добавить", callback_data="admin_add_property")
                ],
                [
                    InlineKeyboardButton("📋 Все бронирования", callback_data="admin_all_bookings"),
                    InlineKeyboardButton("⭐ Все отзывы", callback_data="admin_all_reviews")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            send_telegram_message(
                chat_id,
                text,
                reply_markup=reply_markup.to_dict()
            )
            
            # Update state
            state_data = profile.telegram_state or {}
            state_data['state'] = STATE_ADMIN_DASHBOARD
            profile.telegram_state = state_data
            profile.save()
            
        else:
            send_telegram_message(chat_id, "❌ Ошибка получения статистики")
            
    except Exception as e:
        logger.error(f"Error getting admin dashboard: {e}")
        send_telegram_message(chat_id, "❌ Произошла ошибка")
    
    return True


@log_handler
def handle_edit_property_menu(chat_id: int, property_id: int) -> bool:
    """Show property edit menu"""
    profile = _get_profile(chat_id)
    
    if not check_admin_access(profile):
        return False
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Название", callback_data=f"admin_edit_name_{property_id}"),
            InlineKeyboardButton("📄 Описание", callback_data=f"admin_edit_desc_{property_id}")
        ],
        [
            InlineKeyboardButton("💰 Цена", callback_data=f"admin_edit_price_{property_id}"),
            InlineKeyboardButton("📊 Статус", callback_data=f"admin_edit_status_{property_id}")
        ],
        [
            InlineKeyboardButton("🔐 Коды доступа", callback_data=f"admin_edit_codes_{property_id}")
        ],
        [
            InlineKeyboardButton("« Назад", callback_data=f"admin_property_detail_{property_id}")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    send_telegram_message(
        chat_id,
        "✏️ *Редактирование квартиры*\n\n"
        "Выберите, что хотите изменить:",
        reply_markup=reply_markup.to_dict()
    )
    
    # Update state
    state_data = profile.telegram_state or {}
    state_data['state'] = STATE_ADMIN_PROPERTY_EDIT
    state_data['current_property_id'] = property_id
    profile.telegram_state = state_data
    profile.save()
    
    return True


@log_handler
def handle_edit_access_codes(chat_id: int, property_id: int) -> bool:
    """Show access codes edit menu"""
    profile = _get_profile(chat_id)
    
    if not check_admin_access(profile):
        return False
    
    # Log sensitive operation
    AuditLog.objects.create(
        user=profile.user,
        action='access_property_codes_edit',
        resource_type='Property',
        resource_id=property_id,
        details={'action': 'opened_codes_edit_menu'}
    )
    
    keyboard = [
        [
            InlineKeyboardButton("🏠 Код домофона", callback_data=f"edit_entry_code_{property_id}")
        ],
        [
            InlineKeyboardButton("🗝️ Код сейфа", callback_data=f"edit_key_safe_code_{property_id}")
        ],
        [
            InlineKeyboardButton("🔑 Код замка", callback_data=f"edit_digital_lock_code_{property_id}")
        ],
        [
            InlineKeyboardButton("« Назад", callback_data=f"admin_edit_property_{property_id}")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    send_telegram_message(
        chat_id,
        "🔐 *Управление кодами доступа*\n\n"
        "⚠️ *Внимание!* Все действия с кодами логируются.\n\n"
        "Выберите код для изменения:",
        reply_markup=reply_markup.to_dict()
    )
    
    # Update state
    state_data = profile.telegram_state or {}
    state_data['state'] = STATE_EDIT_ACCESS_CODES
    state_data['current_property_id'] = property_id
    profile.telegram_state = state_data
    profile.save()
    
    return True