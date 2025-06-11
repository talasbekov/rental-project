from django.contrib.auth.models import User
from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property
from booking_bot.bookings.models import Booking
from booking_bot.payments import initiate_payment as kaspi_initiate_payment # Import from payments/__init__.py
from booking_bot.payments import KaspiPaymentError # Import custom error
import logging
import requests
from django.conf import settings
from datetime import datetime, date, timedelta
from django.db import transaction

logger = logging.getLogger(__name__)

def get_api_url(endpoint):
    base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
    return f"{base_url}/api/v1/{endpoint}"

def parse_key_value_params(text_params, expected_keys):
    params = {}
    parts = text_params.split(' ')
    for part in parts:
        if ':' in part:
            key, value = part.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            if key in expected_keys:
                params[key] = value
    return params

def parse_search_params(text_params):
    params = {}
    parts = text_params.split(' ')
    for part in parts:
        if ':' in part:
            key, value = part.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            if key == 'rooms': params['number_of_rooms'] = value
            elif key == 'class': params['property_class'] = value
            elif key == 'area':
                if '-' in value: min_val, max_val = value.split('-', 1); params['area_min'] = min_val; params['area_max'] = max_val
                else: params['area_min'] = value
            elif key == 'sort': params['ordering'] = value
    return params

def handle_unknown_user(from_number, incoming_message_body, twilio_messaging_response):
    logger.info(f"New user from {from_number}. Initiating registration.")
    existing_profile = UserProfile.objects.filter(phone_number=from_number).first()
    if existing_profile:
        logger.warning(f"User profile for {from_number} exists. User: {existing_profile.user.username}")
        twilio_messaging_response.message(f"Welcome back, {existing_profile.user.username}! (Type /help for commands)")
        return

    username = f"user_{from_number.replace('+', '')}"
    try:
        with transaction.atomic():
            user, created = User.objects.get_or_create(username=username, defaults={'first_name': 'WhatsApp User'})
            if created: user.set_unusable_password(); user.save(); logger.info(f"Created User: {username}")

            profile, profile_created = UserProfile.objects.get_or_create(user=user, defaults={'role': 'user', 'phone_number': from_number})
            if profile_created: twilio_messaging_response.message(f"Welcome! Registered as {username}. (Type /help for commands)")
            elif profile.phone_number != from_number:
                profile.phone_number = from_number; profile.save()
                twilio_messaging_response.message(f"Welcome back, {username}! Phone updated. (Type /help for commands)")
            else: twilio_messaging_response.message(f"Welcome back, {username}! (Type /help for commands)")
    except Exception as e:
        logger.error(f"Error during registration for {from_number}: {e}", exc_info=True)
        twilio_messaging_response.message("Error registering. Try again later.")

def handle_known_user(user_profile, incoming_message_body, twilio_messaging_response):
    logger.info(f"Message from {user_profile.user.username} ({user_profile.role}): {incoming_message_body}")
    parts = incoming_message_body.split(' ', 1)
    command = parts[0].lower()
    params_text = parts[1] if len(parts) > 1 else ""

    if command == '/help':
        help_text = ("Available commands:\n"
                     "/search [criteria] - e.g., /search rooms:2 area:100-150\n"
                     "/view <property_id> - View property details\n"
                     "/book property_id:<id> from:YYYY-MM-DD to:YYYY-MM-DD - Book a property\n"
                     "/mybookings - View your bookings\n"
                     "/cancel_booking <booking_id> - Cancel a booking\n"
                     "/pay <booking_id> - Pay for a pending booking\n"
                     )
        twilio_messaging_response.message(help_text)

    elif command == '/search':
        api_params = parse_search_params(params_text)
        try:
            response = requests.get(get_api_url('listings/properties/'), params=api_params)
            response.raise_for_status()
            properties = response.json()
            if properties:
                reply = "Found properties:\n";
                for prop in properties[:5]: reply += f"\nID: {prop['id']} Name: {prop['name']} Price: {prop['price_per_day']} KZT/day\nTo view: /view {prop['id']}\n----\n"
                if len(properties) > 5: reply += f"And {len(properties) - 5} more..."
            else: reply = "No properties found."
            twilio_messaging_response.message(reply)
        except Exception as e: logger.error(f"API Search Error: {e}"); twilio_messaging_response.message("Error searching.")

    elif command == '/view':
        property_id_str = params_text.strip()
        if not property_id_str.isdigit(): twilio_messaging_response.message("Usage: /view <property_id>"); return
        try:
            response = requests.get(get_api_url(f'listings/properties/{property_id_str}/'))
            response.raise_for_status()
            prop = response.json()
            reply = (f"ID: {prop['id']} Name: {prop['name']} Desc: {prop['description']}\n"
                     f"Addr: {prop['address']} Rooms: {prop['number_of_rooms']}, Area: {prop['area']}m²\n"
                     f"Class: {prop['property_class']}, Price: {prop['price_per_day']} KZT/day\n"
                     f"To book: /book property_id:{prop['id']} from:YYYY-MM-DD to:YYYY-MM-DD")
            twilio_messaging_response.message(reply)
        except Exception as e: logger.error(f"API View Error: {e}"); twilio_messaging_response.message("Error viewing property.")

    elif command == '/book':
        expected_keys = ['property_id', 'from', 'to']
        booking_params = parse_key_value_params(params_text, expected_keys)
        prop_id_param_str = booking_params.get('property_id'); start_date_str = booking_params.get('from'); end_date_str = booking_params.get('to')
        if not (prop_id_param_str and start_date_str and end_date_str): twilio_messaging_response.message("Usage: /book property_id:<id> from:YYYY-MM-DD to:YYYY-MM-DD"); return
        try:
            property_id_int = int(prop_id_param_str); start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date(); end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if start_date < date.today(): twilio_messaging_response.message("Start date cannot be in the past."); return
            if end_date <= start_date: twilio_messaging_response.message("End date must be after start date."); return
            selected_property = Property.objects.get(id=property_id_int)
            overlapping = Booking.objects.filter(property=selected_property, start_date__lt=end_date, end_date__gt=start_date, status__in=['pending', 'confirmed']).exists()
            if overlapping: twilio_messaging_response.message(f"Sorry, {selected_property.name} is not available for selected dates."); return
            duration = (end_date - start_date).days; price = duration * selected_property.price_per_day
            with transaction.atomic(): new_booking = Booking.objects.create(user=user_profile.user, property=selected_property, start_date=start_date, end_date=end_date, total_price=price, status='pending')
            logger.info(f"Booking {new_booking.id} created for {user_profile.user.username}")
            twilio_messaging_response.message(f"Booking successful!\nID: {new_booking.id} Prop: {selected_property.name}\nDates: {start_date_str} to {end_date_str}\nTotal: {price} KZT. Status: {new_booking.status}.\nUse /pay {new_booking.id} to confirm.")
        except Property.DoesNotExist: twilio_messaging_response.message(f"Property ID {prop_id_param_str} not found.")
        except ValueError: twilio_messaging_response.message("Invalid ID or date format. Use YYYY-MM-DD.")
        except Exception as e: logger.error(f"Booking Error: {e}", exc_info=True); twilio_messaging_response.message("Error creating booking.")

    elif command == '/mybookings':
        user_bookings = Booking.objects.filter(user=user_profile.user).order_by('-created_at')
        if not user_bookings.exists(): twilio_messaging_response.message("You have no bookings yet."); return
        reply = "Your bookings:\n";
        for booking in user_bookings[:5]:
            reply += (f"\nID: {booking.id} Prop: {booking.property.name}\n"
                      f"Dates: {booking.start_date.strftime('%Y-%m-%d')} to {booking.end_date.strftime('%Y-%m-%d')}\n"
                      f"Total: {booking.total_price} KZT Status: {booking.status.capitalize()}\n")
            if booking.status == 'pending': reply += f"To pay: /pay {booking.id}\n"
            reply += "----\n"
        if user_bookings.count() > 5: reply += f"Showing {len(user_bookings[:5])} of {user_bookings.count()} bookings."
        twilio_messaging_response.message(reply)

    elif command == '/cancel_booking':
        booking_id_str = params_text.strip()
        if not booking_id_str.isdigit(): twilio_messaging_response.message("Usage: /cancel_booking <booking_id>"); return
        try:
            booking_to_cancel = Booking.objects.get(id=int(booking_id_str), user=user_profile.user)
            CANCELLABLE_STATUSES = ['pending', 'confirmed']
            if booking_to_cancel.status not in CANCELLABLE_STATUSES: twilio_messaging_response.message(f"Booking ID {booking_id_str} cannot be cancelled (Status: {booking_to_cancel.status.capitalize()})."); return
            booking_to_cancel.status = 'cancelled'; booking_to_cancel.save()
            logger.info(f"Booking ID {booking_id_str} cancelled by {user_profile.user.username}")
            twilio_messaging_response.message(f"Booking ID {booking_id_str} has been cancelled.")
        except Booking.DoesNotExist: twilio_messaging_response.message(f"Booking ID {booking_id_str} not found or no permission.")
        except ValueError: twilio_messaging_response.message("Invalid Booking ID format.")
        except Exception as e: logger.error(f"Cancel Booking Error: {e}", exc_info=True); twilio_messaging_response.message("Error cancelling booking.")

    elif command == '/pay':
        booking_id_str = params_text.strip()
        if not booking_id_str.isdigit():
            twilio_messaging_response.message("Usage: /pay <booking_id>")
            return
        try:
            booking_id_int = int(booking_id_str)
            booking_to_pay = Booking.objects.get(id=booking_id_int, user=user_profile.user)

            if booking_to_pay.status != 'pending':
                twilio_messaging_response.message(f"Booking ID {booking_id_int} is not pending payment (Status: {booking_to_pay.status.capitalize()}).")
                return

            # Call placeholder Kaspi service
            payment_info = kaspi_initiate_payment(
                booking_id=booking_to_pay.id,
                amount=float(booking_to_pay.total_price), # Ensure amount is float
                description=f"Payment for Booking ID {booking_to_pay.id} - Property {booking_to_pay.property.name}"
            )

            # Create a Payment record in our database - This step will be refined later
            # For now, we just show the Kaspi link.
            # from booking_bot.payments.models import Payment
            # Payment.objects.create(booking=booking_to_pay, amount=booking_to_pay.total_price, payment_method='kaspi_placeholder', transaction_id=payment_info.get('payment_id'), status='pending')

            reply = f"To complete your booking (ID: {booking_to_pay.id}), please proceed to payment:\n"
            reply += f"{payment_info.get('checkout_url')}\n"
            reply += f"Kaspi Payment ID (dummy): {payment_info.get('payment_id')}\n"
            reply += "After payment, your booking status will be updated (this is a manual step for now)."
            twilio_messaging_response.message(reply)

        except Booking.DoesNotExist:
            twilio_messaging_response.message(f"Booking ID {booking_id_str} not found or you don't have permission.")
        except KaspiPaymentError as e: # Catch custom error from Kaspi service
            logger.error(f"Kaspi payment initiation failed for booking {booking_id_str}: {e}")
            twilio_messaging_response.message(f"Could not initiate payment: {e}")
        except Exception as e:
            logger.error(f"Error processing payment for booking {booking_id_str}: {e}", exc_info=True)
            twilio_messaging_response.message("Sorry, an error occurred while processing your payment.")

    elif command == '/add_property' and user_profile.role in ['admin', 'super_admin']:
        twilio_messaging_response.message("Admin: Property addition feature coming soon!")
    else:
        twilio_messaging_response.message(f"Received: '{incoming_message_body}'. Not sure how to handle that. Try /help.")
