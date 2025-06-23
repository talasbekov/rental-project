import json
import logging
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from booking_bot.telegram_bot.handlers import (
    start_command_handler, help_command_handler, callback_query_handler,
    date_input_handler, show_user_bookings, process_review_request
)
from booking_bot.telegram_bot.utils import answer_callback_query

logger = logging.getLogger(__name__)


@csrf_exempt
def telegram_webhook(request):
    """Handle incoming updates from Telegram"""
    if request.method == 'GET':
        return HttpResponse("Telegram webhook is running")

    if request.method != "POST":
        return HttpResponseBadRequest("Method not allowed")

    try:
        data = json.loads(request.body)
        logger.debug(f"Received update: {data}")
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook request")
        return HttpResponseBadRequest("Invalid JSON")

    try:
        # Handle callback queries (button presses)
        if "callback_query" in data:
            callback_query = data["callback_query"]
            callback_id = callback_query["id"]
            chat_id = callback_query["message"]["chat"]["id"]
            message_id = callback_query["message"]["message_id"]
            callback_data = callback_query.get("data", "")

            # Answer callback query to remove loading state
            answer_callback_query(callback_id)

            # Get user info
            from_user = callback_query.get("from", {})
            first_name = from_user.get("first_name")
            last_name = from_user.get("last_name")

            # Handle the callback
            callback_query_handler(chat_id, callback_data, message_id)

            return JsonResponse({"ok": True})

        # Handle regular messages
        elif "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]

            # Get user info
            from_user = message.get("from", {})
            first_name = from_user.get("first_name")
            last_name = from_user.get("last_name")

            # Handle different message types
            if "text" in message:
                text = message["text"].strip()

                # Handle commands
                if text.startswith("/start"):
                    start_command_handler(chat_id, first_name, last_name)
                elif text.startswith("/help"):
                    help_command_handler(chat_id)
                elif text.startswith("/menu"):
                    start_command_handler(chat_id, first_name, last_name)
                elif text.startswith("/bookings"):
                    show_user_bookings(chat_id, 'active')
                elif text.startswith("/history"):
                    show_user_bookings(chat_id, 'completed')
                elif text.startswith("/details_"):
                    # Handle booking details command
                    try:
                        booking_id = int(text.split("_")[1])
                        show_booking_details(chat_id, booking_id)
                    except (IndexError, ValueError):
                        pass
                else:
                    # Handle regular text (e.g., date input)
                    date_input_handler(chat_id, text)

            # Handle photo messages (for reviews)
            elif "photo" in message:
                handle_photo_message(chat_id, message)

            return JsonResponse({"ok": True})

        # Handle other update types if needed
        else:
            logger.info(f"Unhandled update type: {data}")
            return JsonResponse({"ok": True})

    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


def show_booking_details(chat_id, booking_id):
    """Show detailed booking information"""
    from booking_bot.bookings.models import Booking
    from booking_bot.users.models import UserProfile
    from booking_bot.telegram_bot.utils import send_telegram_message

    try:
        profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
        booking = Booking.objects.get(id=booking_id, user=profile.user)

        if booking.status != 'confirmed':
            send_telegram_message(chat_id, "Детали доступны только для подтвержденных бронирований.")
            return

        property_obj = booking.property

        text = (
            f"*Детали бронирования #{booking.id}*\n\n"
            f"🏠 *{property_obj.name}*\n"
            f"📍 Адрес: {property_obj.address}\n"
        )

        # Add access information if available
        if property_obj.entry_instructions:
            text += f"\n📝 *Инструкции:*\n{property_obj.entry_instructions}\n"

        if property_obj.digital_lock_code:
            text += f"\n🔐 Код замка: `{property_obj.digital_lock_code}`\n"
        elif property_obj.key_safe_code:
            text += f"\n🔑 Код сейфа: `{property_obj.key_safe_code}`\n"

        text += (
            f"\n📅 Заезд: {booking.start_date.strftime('%d.%m.%Y')}\n"
            f"📅 Выезд: {booking.end_date.strftime('%d.%m.%Y')}\n"
            f"💰 Оплачено: {booking.total_price} ₸"
        )

        # Add owner contact if available
        if property_obj.owner.profile.phone_number:
            text += f"\n\n📞 Контакт: {property_obj.owner.profile.phone_number}"

        keyboard = [[{"text": "◀️ Назад", "callback_data": "main_current"}]]

        send_telegram_message(chat_id, text, {"inline_keyboard": keyboard})

    except (UserProfile.DoesNotExist, Booking.DoesNotExist):
        send_telegram_message(chat_id, "Бронирование не найдено.")
    except Exception as e:
        logger.error(f"Error showing booking details: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при загрузке деталей.")


def handle_photo_message(chat_id, message):
    """Handle photo uploads (for reviews)"""
    from booking_bot.users.models import UserProfile
    from booking_bot.telegram_bot.utils import send_telegram_message

    try:
        profile = UserProfile.objects.get(telegram_chat_id=str(chat_id))
        state_data = profile.telegram_state or {}

        if state_data.get('state') == 'awaiting_review_photos':
            # Handle review photo upload
            photos = message.get("photo", [])
            if photos:
                # Get the largest photo
                photo = max(photos, key=lambda p: p.get("file_size", 0))
                file_id = photo.get("file_id")

                # Store file_id in state
                review_photos = state_data.get('review_photos', [])
                review_photos.append(file_id)
                state_data['review_photos'] = review_photos

                if len(review_photos) < 3:
                    send_telegram_message(
                        chat_id,
                        f"Фото {len(review_photos)}/3 загружено. Можете добавить еще или нажать 'Готово'.",
                        {"inline_keyboard": [[{"text": "✅ Готово", "callback_data": "submit_review_with_photos"}]]}
                    )
                else:
                    # Auto-submit after 3 photos
                    submit_review_with_photos(chat_id, profile)

                profile.telegram_state = state_data
                profile.save()
        else:
            send_telegram_message(chat_id, "Используйте команду /start для начала работы с ботом.")

    except UserProfile.DoesNotExist:
        send_telegram_message(chat_id, "Пользователь не найден. Используйте /start")
    except Exception as e:
        logger.error(f"Error handling photo message: {e}")


def submit_review_with_photos(chat_id, profile):
    """Submit review with uploaded photos"""
    from booking_bot.listings.models import Review, ReviewPhoto
    from booking_bot.bookings.models import Booking
    from booking_bot.telegram_bot.utils import send_telegram_message, get_file_url

    state_data = profile.telegram_state or {}
    booking_id = state_data.get('review_booking_id')
    rating = state_data.get('review_rating')
    text = state_data.get('review_text', '')
    photo_file_ids = state_data.get('review_photos', [])

    try:
        booking = Booking.objects.get(id=booking_id, user=profile.user)

        # Create review
        review = Review.objects.create(
            property=booking.property,
            user=profile.user,
            rating=rating,
            text=text
        )

        # Add photos
        for file_id in photo_file_ids:
            file_url = get_file_url(file_id)
            if file_url:
                ReviewPhoto.objects.create(
                    review=review,
                    image_url=file_url
                )

        send_telegram_message(chat_id, "Спасибо за ваш отзыв с фотографиями! 📸👍")

        # Clear state
        profile.telegram_state = {}
        profile.save()

    except Exception as e:
        logger.error(f"Error submitting review with photos: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при сохранении отзыва.")