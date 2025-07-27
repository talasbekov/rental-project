import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404 # For cleaner object retrieval

from booking_bot.bookings.models import Booking
from booking_bot.users.models import UserProfile
# Assuming send_whatsapp_message is a utility function you've created
# from booking_bot.whatsapp_bot.utils import send_whatsapp_message
# For now, we'll mock it or log instead of sending actual messages if utils isn't ready
from booking_bot.whatsapp_bot.handlers import clear_user_state

# Add necessary imports:
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated # Or custom permission for bot/service

from . import kaspi_service
# Booking model already imported: from booking_bot.bookings.models import Booking
from .kaspi_service import initiate_payment as kaspi_initiate_payment_service, KaspiPaymentError
# from django.shortcuts import get_object_or_404 # If using this


logger = logging.getLogger(__name__)

# Mock function if actual WhatsApp sending utility is not yet available or for testing
def send_whatsapp_message(phone_number, message_body):
    logger.info(f"MOCK WHATSAPP to {phone_number}: {message_body}")
    # In a real scenario, this would integrate with Twilio or another WhatsApp provider
    # For example:
    # from twilio.rest import Client
    # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    # message = client.messages.create(
    #     body=message_body,
    #     from_=settings.TWILIO_WHATSAPP_NUMBER,
    #     to=f'whatsapp:{phone_number}'
    # )
    # logger.info(f"Sent WhatsApp message SID: {message.sid} to {phone_number}")
    pass


# Обновленная функция kaspi_payment_webhook в payments/views.py

@csrf_exempt
def kaspi_payment_webhook(request):
    """
    Обработка webhook от Kaspi о статусе платежа

    Kaspi отправляет POST запрос с информацией о платеже
    """
    if request.method == 'POST':
        try:
            # Парсим JSON из тела запроса
            data = json.loads(request.body)
            logger.info(f"Kaspi webhook получен: {data}")

            # Проверяем подпись (если Kaspi её отправляет)
            signature = request.headers.get('X-Kaspi-Signature')
            if signature and hasattr(kaspi_service, 'verify_webhook_signature'):
                if not kaspi_service.verify_webhook_signature(data, signature):
                    logger.error("Неверная подпись webhook от Kaspi")
                    return JsonResponse({'status': 'error', 'message': 'Invalid signature'}, status=403)

        except json.JSONDecodeError:
            logger.error("Kaspi webhook: Неверный JSON")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        # Извлекаем данные о платеже
        kaspi_payment_id = data.get('payment_id') or data.get('transactionId')
        payment_status = data.get('status')
        order_id = data.get('order_id') or data.get('orderId')
        amount = data.get('amount')

        # Валидация обязательных полей
        if not kaspi_payment_id:
            logger.error("Kaspi webhook: отсутствует payment_id/transactionId")
            return JsonResponse({'status': 'error', 'message': 'payment_id is required'}, status=400)

        if not payment_status:
            logger.error("Kaspi webhook: отсутствует status")
            return JsonResponse({'status': 'error', 'message': 'status is required'}, status=400)

        try:
            # Ищем бронирование по kaspi_payment_id
            booking = None

            # Сначала пробуем найти по kaspi_payment_id
            try:
                booking = Booking.objects.get(kaspi_payment_id=kaspi_payment_id)
                logger.info(f"Найдено бронирование {booking.id} по kaspi_payment_id")
            except Booking.DoesNotExist:
                # Если не нашли, пробуем по order_id (если он есть)
                if order_id:
                    try:
                        booking = Booking.objects.get(id=int(order_id))
                        # Сохраняем kaspi_payment_id для будущих запросов
                        booking.kaspi_payment_id = kaspi_payment_id
                        booking.save()
                        logger.info(f"Найдено бронирование {booking.id} по order_id")
                    except (Booking.DoesNotExist, ValueError):
                        pass

            if not booking:
                logger.error(f"Kaspi webhook: Бронирование не найдено для payment_id: {kaspi_payment_id}")
                return JsonResponse({'status': 'error', 'message': 'Booking not found'}, status=404)

            # Обрабатываем статус платежа
            # Приводим статус к верхнему регистру для унификации
            status_upper = payment_status.upper()

            # Маппинг статусов Kaspi на наши статусы
            status_mapping = {
                'SUCCESS': 'confirmed',
                'SUCCESSFUL': 'confirmed',
                'COMPLETED': 'confirmed',
                'PAID': 'confirmed',
                'APPROVED': 'confirmed',
                'FAILED': 'payment_failed',
                'DECLINED': 'payment_failed',
                'CANCELLED': 'cancelled',
                'CANCELED': 'cancelled',
                'EXPIRED': 'payment_failed',
                'PENDING': 'pending_payment',
                'PROCESSING': 'pending_payment'
            }

            new_status = status_mapping.get(status_upper)

            if not new_status:
                logger.warning(f"Неизвестный статус платежа от Kaspi: {payment_status}")
                # Для неизвестных статусов оставляем текущий статус
                return JsonResponse({'status': 'success', 'message': 'Status not processed'}, status=200)

            # Обновляем статус только если он изменился
            if booking.status != new_status:
                old_status = booking.status
                booking.status = new_status
                booking.save()

                logger.info(f"Статус бронирования {booking.id} изменен: {old_status} -> {new_status}")

                # Отправляем уведомления при успешной оплате
                if new_status == 'confirmed' and old_status != 'confirmed':
                    try:
                        # Получаем профиль пользователя
                        user_profile = UserProfile.objects.get(user=booking.user)

                        # Отправляем уведомление в Telegram
                        if user_profile.telegram_chat_id:
                            send_telegram_booking_confirmation(user_profile.telegram_chat_id, booking)
                            logger.info(f"Отправлено подтверждение в Telegram для бронирования {booking.id}")

                        # Отправляем уведомление в WhatsApp
                        if user_profile.phone_number:
                            send_whatsapp_booking_confirmation(user_profile.phone_number, booking)
                            logger.info(f"Отправлено подтверждение в WhatsApp для бронирования {booking.id}")

                        # Очищаем состояние пользователя в ботах
                        if hasattr(user_profile, 'telegram_state'):
                            user_profile.telegram_state = {}
                            user_profile.save()

                        if hasattr(user_profile, 'whatsapp_state'):
                            user_profile.whatsapp_state = {}
                            user_profile.save()

                    except UserProfile.DoesNotExist:
                        logger.error(f"UserProfile не найден для пользователя {booking.user.id}")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке уведомлений для бронирования {booking.id}: {e}")

                # Обработка неудачной оплаты
                elif new_status == 'payment_failed':
                    try:
                        user_profile = UserProfile.objects.get(user=booking.user)

                        # Уведомляем пользователя об ошибке
                        error_message = data.get('error_message', 'Платеж не прошел')

                        if user_profile.telegram_chat_id:
                            send_telegram_payment_error(user_profile.telegram_chat_id, booking, error_message)

                        if user_profile.phone_number:
                            send_whatsapp_payment_error(user_profile.phone_number, booking, error_message)

                    except Exception as e:
                        logger.error(f"Ошибка при отправке уведомления об ошибке платежа: {e}")

            else:
                logger.info(f"Статус бронирования {booking.id} не изменился: {booking.status}")

            # Логируем платеж
            if amount:
                try:
                    from booking_bot.payments.models import Payment
                    Payment.objects.update_or_create(
                        booking=booking,
                        transaction_id=kaspi_payment_id,
                        defaults={
                            'amount': float(amount) / 100 if amount > 1000 else amount,
                            # Конвертируем из тиынов если нужно
                            'payment_method': 'kaspi',
                            'status': new_status
                        }
                    )
                except Exception as e:
                    logger.error(f"Ошибка при сохранении информации о платеже: {e}")

            # Возвращаем успешный ответ Kaspi
            return JsonResponse({
                'status': 'success',
                'message': 'Webhook processed',
                'booking_id': booking.id,
                'new_status': new_status
            }, status=200)

        except Exception as e:
            logger.error(f"Ошибка при обработке Kaspi webhook: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': 'Internal server error'}, status=500)

    else:
        # GET запрос - возвращаем информацию о webhook
        return HttpResponse("Kaspi payment webhook endpoint", status=200)


def send_telegram_booking_confirmation(telegram_chat_id, booking):
    """Отправка подтверждения бронирования в Telegram"""
    from booking_bot.telegram_bot.utils import send_telegram_message
    from telegram import KeyboardButton, ReplyKeyboardMarkup

    property_obj = booking.property

    text = (
        f"✅ *Оплата подтверждена!*\n\n"
        f"🎉 Ваше бронирование успешно оформлено!\n\n"
        f"📋 *Детали бронирования:*\n"
        f"Номер брони: #{booking.id}\n"
        f"Квартира: {property_obj.name}\n"
        f"Адрес: {property_obj.address}\n"
        f"Заезд: {booking.start_date.strftime('%d.%m.%Y')}\n"
        f"Выезд: {booking.end_date.strftime('%d.%m.%Y')}\n"
        f"Стоимость: {booking.total_price:,.0f} ₸\n\n"
    )

    if property_obj.entry_instructions:
        text += f"📝 *Инструкции:*\n{property_obj.entry_instructions}\n\n"

    if property_obj.digital_lock_code:
        text += f"🔐 *Код замка:* `{property_obj.digital_lock_code}`\n"
    elif property_obj.key_safe_code:
        text += f"🔑 *Код сейфа:* `{property_obj.key_safe_code}`\n"

    kb = [
        [KeyboardButton("📊 Мои бронирования")],
        [KeyboardButton("🧭 Главное меню")]
    ]

    send_telegram_message(
        telegram_chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict()
    )


def send_telegram_payment_error(telegram_chat_id, booking, error_message):
    """Отправка уведомления об ошибке платежа в Telegram"""
    from booking_bot.telegram_bot.utils import send_telegram_message
    from telegram import KeyboardButton, ReplyKeyboardMarkup

    text = (
        f"❌ *Ошибка оплаты*\n\n"
        f"К сожалению, оплата бронирования #{booking.id} не прошла.\n"
        f"Причина: {error_message}\n\n"
        f"Попробуйте забронировать снова или обратитесь в поддержку."
    )

    kb = [
        [KeyboardButton("🔍 Поиск квартир")],
        [KeyboardButton("🧭 Главное меню")]
    ]

    send_telegram_message(
        telegram_chat_id,
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True).to_dict()
    )


def send_whatsapp_booking_confirmation(phone_number, booking):
    """Отправка подтверждения бронирования в WhatsApp"""
    from booking_bot.whatsapp_bot.utils import send_whatsapp_message

    property_obj = booking.property

    message = (
        f"✅ Оплата подтверждена!\n\n"
        f"Бронирование #{booking.id}\n"
        f"Квартира: {property_obj.name}\n"
        f"Адрес: {property_obj.address}\n"
        f"Заезд: {booking.start_date.strftime('%d.%m.%Y')}\n"
        f"Выезд: {booking.end_date.strftime('%d.%m.%Y')}\n"
    )

    if property_obj.digital_lock_code:
        message += f"\nКод замка: {property_obj.digital_lock_code}"
    elif property_obj.key_safe_code:
        message += f"\nКод сейфа: {property_obj.key_safe_code}"

    send_whatsapp_message(phone_number, message)


def send_whatsapp_payment_error(phone_number, booking, error_message):
    """Отправка уведомления об ошибке платежа в WhatsApp"""
    from booking_bot.whatsapp_bot.utils import send_whatsapp_message

    message = (
        f"❌ Ошибка оплаты бронирования #{booking.id}\n"
        f"Причина: {error_message}\n"
        f"Попробуйте забронировать снова."
    )

    send_whatsapp_message(phone_number, message)

# Example of how you might have a simple Payment model if you weren't updating Booking directly
# from django.db import models
# class Payment(models.Model):
#     booking = models.ForeignKey(Booking, on_delete=models.CASCADE)
#     kaspi_payment_id = models.CharField(max_length=255, unique=True)
#     status = models.CharField(max_length=50) # e.g., 'pending', 'successful', 'failed'
#     amount = models.DecimalField(max_digits=10, decimal_places=2)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     def __str__(self):
#         return f"Payment {self.kaspi_payment_id} for Booking {self.booking.id} - {self.status}"


class KaspiInitiatePaymentView(APIView):
    permission_classes = [IsAuthenticated] # Ensure only authenticated users/services can call this

    def post(self, request, *args, **kwargs):
        booking_id = request.data.get('booking_id')
        # amount = request.data.get('amount') # Amount can be fetched from booking

        if not booking_id:
            return Response({'error': 'Booking ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking = Booking.objects.get(id=booking_id, user=request.user) # Ensure user owns booking
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found or access denied.'}, status=status.HTTP_404_NOT_FOUND)

        if booking.status not in ['pending', 'pending_payment', 'payment_failed']: # Check current status
             return Response({'error': f'Booking status is "{booking.get_status_display()}", cannot initiate payment.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment_info = kaspi_initiate_payment_service(
                booking_id=booking.id,
                amount=float(booking.total_price), # Ensure amount is float
                description=f"Payment for Booking ID {booking.id} - Property {booking.property.name if booking.property else 'N/A'}"
            )

            if payment_info and payment_info.get('checkout_url') and payment_info.get('payment_id'):
                booking.kaspi_payment_id = payment_info['payment_id']
                booking.status = 'pending_payment' # Set status
                booking.save()

                logger.info(f"Kaspi payment initiated for Booking ID {booking.id}. Kaspi ID: {payment_info['payment_id']}")
                return Response({
                    'checkout_url': payment_info['checkout_url'],
                    'kaspi_payment_id': payment_info['payment_id'],
                    'booking_id': booking.id
                }, status=status.HTTP_200_OK)
            else:
                logger.error(f"Kaspi service failed to return checkout_url or payment_id for Booking ID {booking.id}. Response: {payment_info}")
                # Optionally set booking status to payment_failed here if appropriate
                # booking.status = 'payment_failed'
                # booking.save()
                return Response({'error': 'Payment initiation failed with Kaspi service.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except KaspiPaymentError as e:
            logger.error(f"KaspiPaymentError for Booking ID {booking.id}: {e}", exc_info=True)
            booking.status = 'payment_failed' # Set status on error from Kaspi
            booking.save()
            return Response({'error': f'Kaspi payment error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"Unexpected error initiating payment for Booking ID {booking.id}: {e}", exc_info=True)
            # Consider if status should be 'payment_failed' here
            return Response({'error': 'An unexpected server error occurred.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
