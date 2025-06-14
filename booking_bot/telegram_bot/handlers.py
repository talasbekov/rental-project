import logging
from django.conf import settings
import requests # For calling the new API endpoint
from booking_bot.users.models import UserProfile
from django.contrib.auth.models import User
from django.db import transaction
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler # Added import

logger = logging.getLogger(__name__)


# Define constants for new states
ACTION_SEARCH_STARTED = 'search_started'
ACTION_SEARCH_SELECTING_REGION = 'search_selecting_region'
ACTION_SEARCH_SELECTING_ROOMS = 'search_selecting_rooms'
ACTION_SEARCH_SELECTING_CLASS = 'search_selecting_class'
# Add more as needed, e.g., for pagination: ACTION_SEARCH_DISPLAYING_RESULTS
ACTION_BOOKING_AWAITING_START_DATE = 'booking_awaiting_start_date'
ACTION_BOOKING_AWAITING_END_DATE = 'booking_awaiting_end_date'

# Placeholder for getting regions, rooms, classes - ideally from DB or config
# Using keys from Property model for consistency with filtering.
# (key, display_name)
AVAILABLE_REGIONS = [
    ('yesil', 'Yesil District'),
    ('nurinsky', 'Nurinsky District'),
    ('almaty', 'Almaty District'),
    ('saryarkinsky', 'Saryarkinsky District'),
    ('baikonursky', 'Baikonursky District'),
]
AVAILABLE_ROOM_COUNTS = ["1", "2", "3", "4+"] # API might take number or string
# Using keys from Property model for property_class
AVAILABLE_PROPERTY_CLASSES = [
    ('economy', 'Economy'),
    ('business', 'Business'), # Model has 'business', prompt had 'Comfort'
    ('luxury', 'Luxury'),   # Model has 'luxury', prompt had 'Premium'
]

# Helper to find display name by key
def get_region_display_name(key):
    for k, name in AVAILABLE_REGIONS:
        if k == key:
            return name
    return key # fallback

def get_class_display_name(key):
    for k, name in AVAILABLE_PROPERTY_CLASSES:
        if k == key:
            return name
    return key # fallback


def get_user_telegram_state(user_profile):
    if isinstance(user_profile.telegram_state, dict):
        return user_profile.telegram_state
    # Add JSON string parsing if necessary from old data, though new field should be dict
    return {'action': None, 'data': {}}

def set_user_telegram_state(user_profile, action, data=None):
    current_data = get_user_telegram_state(user_profile).get('data', {})
    if data is not None:
        current_data.update(data) # Merge new data with existing
    user_profile.telegram_state = {'action': action, 'data': current_data}
    user_profile.save()
    logger.info(f"Set telegram_state for chat_id {user_profile.telegram_chat_id}: action={action}, data={current_data}")


BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN # Assuming TELEGRAM_BOT_TOKEN will be in settings

def get_or_create_user_and_get_token(chat_id, first_name, last_name, phone_number=None):
    # This function will call the new API endpoint
    api_url = f"{settings.SITE_URL}/api/v1/telegram_auth/register_or_login/"
    payload = {
        'telegram_chat_id': chat_id,
        'first_name': first_name,
        'last_name': last_name,
    }
    if phone_number:
        payload['phone_number'] = phone_number

    try:
        response = requests.post(api_url, json=payload)
        response.raise_for_status()
        return response.json() # Expecting {'access': '...', 'refresh': '...'}
    except requests.exceptions.RequestException as e:
        logger.error(f"API call to register_or_login failed: {e}")
        return None

async def start_command_handler(update, context):
    telegram_user = update.effective_user
    chat_id = str(telegram_user.id)
    first_name = telegram_user.first_name
    last_name = telegram_user.last_name or ""

    logger.info(f"/start command received from chat_id {chat_id} ({first_name} {last_name})")

    # For now, just try to get/create user and log token.
    # Actual user creation/update logic will be in the API.
    auth_data = get_or_create_user_and_get_token(chat_id, first_name, last_name)

    if auth_data and auth_data.get('access'):
        logger.info(f"Successfully obtained token for chat_id {chat_id}")
        await update.message.reply_text(
            f"Welcome {first_name}! You are successfully registered/logged in."
        )
        # Store token in context.user_data or similar if needed for session
        context.user_data['jwt_access_token'] = auth_data['access']
        context.user_data['jwt_refresh_token'] = auth_data.get('refresh')
    else:
        logger.error(f"Failed to obtain token for chat_id {chat_id}")
        await update.message.reply_text(
            "Sorry, there was an issue processing your registration. Please try again later."
        )

    # Placeholder for requesting phone number with a button (to be implemented later)
    # from telegram import KeyboardButton, ReplyKeyboardMarkup
    # phone_button = KeyboardButton(text="Share Phone Number", request_contact=True)
    # reply_markup = ReplyKeyboardMarkup([[phone_button]], one_time_keyboard=True)
    # await update.message.reply_text("Please share your phone number to complete registration:", reply_markup=reply_markup)


async def search_command_handler(update, context):
    chat_id = str(update.effective_chat.id)
    user_profile = UserProfile.objects.filter(telegram_chat_id=chat_id).first()

    if not user_profile:
        await update.message.reply_text("Please /start the bot first to register.")
        return

    set_user_telegram_state(user_profile, ACTION_SEARCH_SELECTING_REGION, data={}) # Reset search data

    keyboard = []
    for key, display_name in AVAILABLE_REGIONS:
        keyboard.append([InlineKeyboardButton(display_name, callback_data=f"search_region_{key}")]) # Use key in callback

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Let\'s find an apartment! Please select a region:', reply_markup=reply_markup)


async def search_region_callback_handler(update, context):
    query = update.callback_query
    await query.answer() # Acknowledge callback

    chat_id = str(query.message.chat_id)
    user_profile = UserProfile.objects.filter(telegram_chat_id=chat_id).first()
    if not user_profile:
        await query.edit_message_text("Error: User not found. Please /start again.")
        return

    selected_region_key = query.data.replace("search_region_", "")
    set_user_telegram_state(user_profile, ACTION_SEARCH_SELECTING_ROOMS, data={'region': selected_region_key})

    logger.info(f"Chat {chat_id}: Selected region key {selected_region_key}. Current state: {user_profile.telegram_state}")
    selected_region_display = get_region_display_name(selected_region_key)

    keyboard = []
    for rooms in AVAILABLE_ROOM_COUNTS:
        keyboard.append([InlineKeyboardButton(f"{rooms} rooms", callback_data=f"search_rooms_{rooms}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Region: {selected_region_display}.\nNow, select number of rooms:", reply_markup=reply_markup)

async def search_rooms_callback_handler(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = str(query.message.chat_id)
    user_profile = UserProfile.objects.filter(telegram_chat_id=chat_id).first()
    if not user_profile:
        await query.edit_message_text("Error: User not found. Please /start again.")
        return

    selected_rooms_str = query.data.replace("search_rooms_", "")
    # Clean up "4+" to 4 if needed by API, or handle range
    if selected_rooms_str == "4+": selected_rooms_api = 4 # Assuming API takes a number, and 4 means 4 or more
    else: selected_rooms_api = int(selected_rooms_str)

    current_state_data = get_user_telegram_state(user_profile).get('data', {})
    current_state_data['rooms'] = selected_rooms_api # Store API compatible value

    set_user_telegram_state(user_profile, ACTION_SEARCH_SELECTING_CLASS, data=current_state_data)
    region_display = get_region_display_name(current_state_data.get('region'))
    logger.info(f"Chat {chat_id}: Selected rooms {selected_rooms_str}. Current state: {user_profile.telegram_state}")

    keyboard = []
    for key, display_name in AVAILABLE_PROPERTY_CLASSES:
        keyboard.append([InlineKeyboardButton(display_name, callback_data=f"search_class_{key}")]) # Use key in callback
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Region: {region_display}, Rooms: {selected_rooms_str}.\nSelect property class:", reply_markup=reply_markup)

async def search_class_callback_handler(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = str(query.message.chat_id)
    user_profile = UserProfile.objects.filter(telegram_chat_id=chat_id).first()
    if not user_profile:
        await query.edit_message_text("Error: User not found. Please /start again.")
        return

    selected_class_key = query.data.replace("search_class_", "")

    current_state_data = get_user_telegram_state(user_profile).get('data', {})
    current_state_data['class'] = selected_class_key

    # All filters collected, transition to displaying results (or directly call fetch)
    set_user_telegram_state(user_profile, ACTION_SEARCH_STARTED, data=current_state_data) # Or a new state like ACTION_FETCHING_RESULTS
    logger.info(f"Chat {chat_id}: Selected class key {selected_class_key}. All filters collected: {user_profile.telegram_state}")

    region_display = get_region_display_name(current_state_data.get('region'))
    # Assuming 'rooms' stored in current_state_data is display-friendly (e.g., "4+" or "2")
    # If search_rooms_callback_handler stored selected_rooms_str, use that. It stores selected_rooms_api.
    # For display, we might want the original string e.g. "4+"
    rooms_display = current_state_data.get('rooms') # This is currently the API value (e.g. 4)
    # To get the display string for rooms (e.g. "4+"), we might need to re-map or store it.
    # For now, using the API value for rooms in the confirmation.
    class_display = get_class_display_name(selected_class_key)

    await query.edit_message_text(f"Filters complete: Region: {region_display}, Rooms: {rooms_display}, Class: {class_display}.\nFetching apartments...")

    # Call the function to fetch and display apartments
    await fetch_and_display_apartments(update, context, user_profile, current_state_data)

async def fetch_and_display_apartments(update, context, user_profile, filters):
    # Placeholder: This function will call the API and display results

    api_url = f"{settings.SITE_URL}/api/v1/properties/"
    # Construct query params from filters
    params = {
        'region': filters.get('region'), # Should be key like 'yesil'
        'number_of_rooms': filters.get('rooms'), # Should be number like 2 or 4
        'property_class': filters.get('class'), # Should be key like 'economy'
        'status': 'available' # Assuming we always search for available properties
    }
    # Remove None params
    params = {k: v for k, v in params.items() if v is not None}

    logger.info(f"Calling API: {api_url} with params: {params}")

    try:
        # Make the API call (synchronous requests for now)
        response = requests.get(api_url, params=params, headers={'Authorization': f'Bearer {context.user_data.get("jwt_access_token")}'})
        response.raise_for_status() # Raise an exception for HTTP errors
        properties_data = response.json()

        reply_message_target = update.callback_query.message # Target for replies

        if properties_data and isinstance(properties_data, list): # Non-paginated, direct list
            if len(properties_data) > 0:
                await reply_message_target.reply_text(f"Found {len(properties_data)} properties. First one: {properties_data[0].get('name', 'N/A')}")
            else:
                await reply_message_target.reply_text("No apartments found matching your criteria.")
        elif properties_data and isinstance(properties_data, dict) and 'results' in properties_data: # Paginated response
            results = properties_data['results']
            count = properties_data['count']
            if count > 0:
                 await reply_message_target.reply_text(f"Found {count} properties. First one: {results[0].get('name', 'N/A')}")
            else:
                await reply_message_target.reply_text("No apartments found matching your criteria.")
        else:
            # This case handles empty list from non-paginated, or unexpected structure
            await reply_message_target.reply_text("No apartments found matching your criteria, or unexpected API response format.")

    except requests.exceptions.HTTPError as e:
        logger.error(f"API HTTP Error fetching apartments: {e.response.status_code} - {e.response.text}")
        await update.callback_query.message.reply_text(f"Error fetching apartments: API returned {e.response.status_code}. Please try again.")
    except requests.exceptions.RequestException as e:
        logger.error(f"API RequestException fetching apartments: {e}")
        await update.callback_query.message.reply_text("Could not connect to the apartment service. Please try again later.")
    except Exception as e:
        logger.error(f"Unexpected error in fetch_and_display_apartments: {e}", exc_info=True)
        await update.callback_query.message.reply_text("An unexpected error occurred. Please try again.")

    # Clear state after search attempt or set to a results state
    set_user_telegram_state(user_profile, None, {}) # Clear state


async def fetch_and_display_apartments(update, context, user_profile, filters):
    api_url = f"{settings.SITE_URL}/api/v1/properties/"
    params = {
        'region': filters.get('region'),
        'number_of_rooms': filters.get('rooms'),
        'property_class': filters.get('class'),
        'status': 'available'
    }
    params = {k: v for k, v in params.items() if v is not None}
    logger.info(f"Calling API: {api_url} with params: {params}")

    try:
        response = requests.get(api_url, params=params, headers={'Authorization': f'Bearer {context.user_data.get("jwt_access_token")}'})
        response.raise_for_status()
        properties_data = response.json()

        results_to_display = []
        total_count = 0

        if isinstance(properties_data, list): # Non-paginated
            results_to_display = properties_data
            total_count = len(properties_data)
        elif isinstance(properties_data, dict) and 'results' in properties_data: # Paginated
            results_to_display = properties_data['results']
            total_count = properties_data['count']

        reply_message_target = update.callback_query.message

        if not results_to_display:
            await reply_message_target.reply_text("No apartments found matching your criteria.")
            return

        await reply_message_target.reply_text(f"Found {total_count} properties. Displaying up to 5:")

        for prop in results_to_display[:5]: # Limit to first 5 results
            prop_id = prop.get('id')
            details = (
                f"<b>{prop.get('name', 'N/A')}</b>\n"
                f"Price: {prop.get('price_per_day', 'N/A')} KZT/day\n"
                f"Rooms: {prop.get('number_of_rooms', 'N/A')}\n"
                f"Class: {get_class_display_name(prop.get('property_class', 'N/A'))}\n" # Use display name for class
                f"Area: {prop.get('area', 'N/A')} m²"
            )

            keyboard = [[InlineKeyboardButton("Book this apartment", callback_data=f"book_property_{prop_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Assuming PropertySerializer includes 'photos' and it's a list of {'image_url': '...'}
            photo_url = None
            if prop.get('photos') and isinstance(prop['photos'], list) and len(prop['photos']) > 0:
                photo_url = prop['photos'][0].get('image_url')

            if photo_url:
                try:
                    await context.bot.send_photo(
                        chat_id=reply_message_target.chat_id,
                        photo=photo_url,
                        caption=details,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                except Exception as e_photo: # Catch potential errors with photo sending (e.g. URL invalid, too large)
                    logger.error(f"Error sending photo for property {prop_id}: {e_photo}. Sending text message instead.")
                    await context.bot.send_message(
                        chat_id=reply_message_target.chat_id,
                        text=details,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
            else:
                await context.bot.send_message(
                    chat_id=reply_message_target.chat_id,
                    text=details,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )

        # Placeholder for "Next Page" button if total_count > len(results_to_display)
        # This would require handling pagination state (current page/offset)

    except requests.exceptions.HTTPError as e:
        logger.error(f"API HTTP Error fetching apartments: {e.response.status_code} - {e.response.text}")
        error_message = "Sorry, there was an error fetching apartments from the server."
        if e.response.status_code == 401:
            error_message += " Your session might have expired. Please try /start again."
        elif e.response.status_code == 404:
            error_message = "No apartments found matching your criteria (API 404)." # Should be caught by empty results ideally
        else:
            error_message += f" (Error code: {e.response.status_code})"
        await update.callback_query.message.reply_text(error_message)
    except requests.exceptions.RequestException as e:
        logger.error(f"API RequestException fetching apartments: {e}")
        await update.callback_query.message.reply_text("We're having trouble connecting to our apartment listings. Please try again in a moment.")
    except Exception as e:
        logger.error(f"Unexpected error in fetch_and_display_apartments: {e}", exc_info=True)
        await update.callback_query.message.reply_text("An unexpected error occurred while searching for apartments. Please try again.")
    finally:
        # Clear state after search attempt or set to a results state
        set_user_telegram_state(user_profile, None, {}) # Clear state


async def book_property_callback_handler(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = str(query.message.chat_id)
    user_profile = UserProfile.objects.filter(telegram_chat_id=chat_id).first()
    if not user_profile:
        await context.bot.send_message(chat_id=chat_id, text="Error: User profile not found. Please /start again.")
        return

    property_id = query.data.replace("book_property_", "")
    logger.info(f"Chat {chat_id}: Initiating booking for property ID {property_id}")

    # Store property_id and set state to await start date
    set_user_telegram_state(user_profile, ACTION_BOOKING_AWAITING_START_DATE, data={'property_id': property_id})

    # Fetch property details to show name (optional, but good UX)
    property_name = f"Property ID {property_id}" # Fallback name
    try:
        api_url = f"{settings.SITE_URL}/api/v1/properties/{property_id}/"
        response = requests.get(api_url, headers={'Authorization': f'Bearer {context.user_data.get("jwt_access_token")}'})
        if response.status_code == 200:
            property_name = response.json().get('name', property_name)
    except Exception as e:
        logger.error(f"Error fetching property details for ID {property_id}: {e}")

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"You are booking: {property_name}.\nPlease send the check-in date (YYYY-MM-DD)."
    )

# Need to import date and datetime from datetime
from datetime import datetime, date
import json # For create_booking_in_api error handling

async def create_booking_in_api(update, context, user_profile, booking_data):
    logger.info(f"Attempting to create booking for user {user_profile.telegram_chat_id} with data: {booking_data}")
    api_url = f"{settings.SITE_URL}/api/v1/bookings/"
    payload = {
        'property_id': booking_data.get('property_id'),
        'start_date': booking_data.get('start_date'),
        'end_date': booking_data.get('end_date'),
        # user_id will be derived from JWT on the backend
    }

    try:
        response = requests.post(api_url, json=payload, headers={'Authorization': f'Bearer {context.user_data.get("jwt_access_token")}'})
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        booking_response_data = response.json()
        booking_id_from_booking_api = booking_response_data.get('id') # Corrected variable name
        total_price = booking_response_data.get('total_price')

        # --- Add this section ---
        if booking_id_from_booking_api and total_price is not None:
            logger.info(f"Booking {booking_id_from_booking_api} created. Now initiating payment.")
            payment_initiation_url = f"{settings.SITE_URL}/api/v1/payments/kaspi/initiate/"
            payment_payload = {
                'booking_id': booking_id_from_booking_api
                # 'amount': total_price # Amount is fetched from booking by the new API view
            }
            try:
                payment_response = requests.post(
                    payment_initiation_url,
                    json=payment_payload,
                    headers={'Authorization': f'Bearer {context.user_data.get("jwt_access_token")}'}
                )
                payment_response.raise_for_status()
                payment_data = payment_response.json()
                checkout_url = payment_data.get('checkout_url')

                if checkout_url:
                    logger.info(f"Kaspi payment link obtained for booking {booking_id_from_booking_api}: {checkout_url}")
                    keyboard = [[InlineKeyboardButton("Proceed to Kaspi Pay", url=checkout_url)]]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    original_success_message = f"Booking created successfully! Booking ID: {booking_id_from_booking_api}, Total Price: {total_price} KZT."
                    await context.bot.send_message(
                        chat_id=user_profile.telegram_chat_id,
                        text=f"{original_success_message}\nPlease complete your payment using the link below:",
                        reply_markup=reply_markup
                    )
                    set_user_telegram_state(user_profile, None, {}) # Clear state as booking process (pre-payment) is done
                    return True # Indicate overall success of booking + payment initiation
                else:
                    logger.error(f"Payment initiation succeeded but no checkout_url for booking {booking_id_from_booking_api}. Response: {payment_data}")
                    await context.bot.send_message(
                        chat_id=user_profile.telegram_chat_id,
                        text=f"Booking {booking_id_from_booking_api} created, but payment link could not be generated. Please contact support."
                    )
                    set_user_telegram_state(user_profile, None, {})
                    return False # Partial success, booking made but payment link failed

            except requests.exceptions.HTTPError as e_pay:
                error_msg_pay = "Booking created, but failed to initiate payment."
                if e_pay.response is not None:
                    try:
                        error_details_pay = e_pay.response.json()
                        if isinstance(error_details_pay, dict):
                            api_errors_pay = []
                            for k_pay, v_pay in error_details_pay.items():
                                if isinstance(v_pay, list): api_errors_pay.append(f"{k_pay}: {', '.join(v_pay)}")
                                else: api_errors_pay.append(f"{k_pay}: {v_pay}")
                            if api_errors_pay: error_msg_pay += " Errors: " + "; ".join(api_errors_pay)
                        else: error_msg_pay += f" API Error: {e_pay.response.text}"
                    except json.JSONDecodeError:
                        error_msg_pay += f" API Error: {e_pay.response.status_code} - {e_pay.response.text}"
                else: error_msg_pay += f" HTTP Error: {str(e_pay)}"
                logger.error(f"API HTTPError initiating payment for booking {booking_id_from_booking_api}: {error_msg_pay}", exc_info=True)
                await context.bot.send_message(chat_id=user_profile.telegram_chat_id, text=f"{error_msg_pay} Please contact support quoting Booking ID {booking_id_from_booking_api}.")
                set_user_telegram_state(user_profile, None, {})
                return False # Partial success
            except requests.exceptions.RequestException as e_pay_req:
                logger.error(f"API RequestException initiating payment for booking {booking_id_from_booking_api}: {e_pay_req}", exc_info=True)
                await context.bot.send_message(chat_id=user_profile.telegram_chat_id, text=f"Booking created, but could not connect to payment service for Booking ID {booking_id_from_booking_api}. Please contact support.")
                set_user_telegram_state(user_profile, None, {})
                return False # Partial success
            except Exception as e_unexp_pay:
                logger.error(f"Unexpected error initiating payment for booking {booking_id_from_booking_api}: {e_unexp_pay}", exc_info=True)
                await context.bot.send_message(chat_id=user_profile.telegram_chat_id, text=f"Booking created, but an unexpected error occurred while initiating payment for Booking ID {booking_id_from_booking_api}. Please contact support.")
                set_user_telegram_state(user_profile, None, {})
                return False
        else: # If booking_id_from_booking_api or total_price was missing from booking creation response
            logger.error(f"Booking creation response missing ID or total_price for chat {user_profile.telegram_chat_id}. Response: {booking_response_data}")
            await context.bot.send_message(chat_id=user_profile.telegram_chat_id, text="Booking confirmation details incomplete. Please contact support.")
            set_user_telegram_state(user_profile, None, {})
            return False
        # --- End of new section ---

    except requests.exceptions.HTTPError as e:
        error_message = "Failed to create booking."
        if e.response is not None:
            try:
                error_details = e.response.json()
                if isinstance(error_details, dict):
                     # Extract specific error messages if backend provides them
                    api_errors = []
                    for k, v in error_details.items():
                        if isinstance(v, list): api_errors.append(f"{k}: {', '.join(v)}")
                        else: api_errors.append(f"{k}: {v}")
                    if api_errors: error_message += " Errors: " + "; ".join(api_errors)
                else: # if error_details is not a dict (e.g. plain text error)
                    error_message += f" API Error: {e.response.text}"
            except json.JSONDecodeError:
                error_message += f" API Error: {e.response.status_code} - {e.response.text}"
        else: # If e.response is None
             error_message += f" HTTP Error: {str(e)}"

        logger.error(f"API HTTPError creating booking for chat {user_profile.telegram_chat_id}: {error_message}", exc_info=True)
        await context.bot.send_message(chat_id=user_profile.telegram_chat_id, text=error_message)
        set_user_telegram_state(user_profile, None, {}) # Clear state on failure
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"API RequestException creating booking for chat {user_profile.telegram_chat_id}: {e}", exc_info=True)
        await context.bot.send_message(chat_id=user_profile.telegram_chat_id, text="Could not connect to booking service. Please try again later.")
        set_user_telegram_state(user_profile, None, {}) # Clear state on failure
        return False
    except Exception as e:
        logger.error(f"Unexpected error in create_booking_in_api for {user_profile.telegram_chat_id}: {e}", exc_info=True)
        await context.bot.send_message(chat_id=user_profile.telegram_chat_id, text="An unexpected error occurred while creating your booking.")
        set_user_telegram_state(user_profile, None, {}) # Clear state on failure
        return False


async def date_input_handler(update, context):
    chat_id = str(update.message.chat_id)
    user_profile = UserProfile.objects.filter(telegram_chat_id=chat_id).first()

    if not user_profile: # Should not happen if /start is enforced
        await update.message.reply_text("Please /start the bot first.")
        return

    user_state_info = get_user_telegram_state(user_profile)
    current_action = user_state_info.get('action')
    state_data = user_state_info.get('data', {})
    text_input = update.message.text.strip()

    if current_action == ACTION_BOOKING_AWAITING_START_DATE:
        try:
            start_date_obj = datetime.strptime(text_input, "%Y-%m-%d").date()
            if start_date_obj < date.today():
                await update.message.reply_text("Check-in date cannot be in the past. Please enter a valid date (YYYY-MM-DD).")
                return

            state_data['start_date'] = text_input
            set_user_telegram_state(user_profile, ACTION_BOOKING_AWAITING_END_DATE, data=state_data)
            await update.message.reply_text("Got it. Now, please send the check-out date (YYYY-MM-DD).")
        except ValueError:
            await update.message.reply_text("Invalid date format. Please use YYYY-MM-DD.")
        return

    elif current_action == ACTION_BOOKING_AWAITING_END_DATE:
        try:
            end_date_obj = datetime.strptime(text_input, "%Y-%m-%d").date()
            start_date_obj = datetime.strptime(state_data.get('start_date'), "%Y-%m-%d").date()

            if end_date_obj <= start_date_obj:
                await update.message.reply_text("Check-out date must be after the check-in date. Please enter a valid check-out date (YYYY-MM-DD).")
                return

            state_data['end_date'] = text_input
            # All data collected, attempt to create booking
            await create_booking_in_api(update, context, user_profile, state_data)
            # State will be cleared by create_booking_in_api on success/failure

        except ValueError:
            await update.message.reply_text("Invalid date format for check-out. Please use YYYY-MM-DD.")
        except KeyError: # start_date missing from state_data
             await update.message.reply_text("Error: Start date not found. Please restart the booking process.")
             set_user_telegram_state(user_profile, None, {}) # Clear state
        return

    # If the message is not expected for booking dates, you might want to add a generic reply
    # or ignore it if other handlers (like command handlers) should take precedence.
    # For now, if not in a booking state, this handler does nothing further.


async def my_bookings_command_handler(update, context):
    chat_id = str(update.effective_chat.id)
    user_profile = UserProfile.objects.filter(telegram_chat_id=chat_id).first()

    if not user_profile:
        await update.message.reply_text("Please /start the bot first to register.")
        return

    if not context.user_data.get('jwt_access_token'):
        await update.message.reply_text("Authentication token not found. Please /start again.")
        return

    api_url = f"{settings.SITE_URL}/api/v1/my-bookings/"
    try:
        response = requests.get(api_url, headers={'Authorization': f'Bearer {context.user_data.get("jwt_access_token")}'})
        response.raise_for_status()
        bookings = response.json()

        if not bookings: # API returns list directly, or paginated with 'results'
            await update.message.reply_text("You have no active bookings.")
            return

        results_list = bookings if isinstance(bookings, list) else bookings.get('results', [])
        if not results_list:
            await update.message.reply_text("You have no active bookings.")
            return

        await update.message.reply_text("Here are your bookings:")
        for booking in results_list[:5]: # Display up to 5 bookings
            prop_name = booking.get('property_details', {}).get('name', f"ID {booking.get('property')}")
            status_display = booking.get('status_display', booking.get('status', 'N/A').capitalize())

            start_date_str = booking.get('start_date', 'N/A')
            end_date_str = booking.get('end_date', 'N/A')
            try: # Ensure datetime is imported: from datetime import datetime
                if 'T' in start_date_str: start_date_str = datetime.fromisoformat(start_date_str.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                if 'T' in end_date_str: end_date_str = datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).strftime('%Y-%m-%d')
            except (ValueError, TypeError): # Catch TypeError if date strings are not strings
                logger.warning(f"Could not parse date strings for booking {booking.get('id')}: {start_date_str}, {end_date_str}")
                pass # Keep original if parsing fails

            booking_info = (
                f"Booking ID: {booking.get('id')}\n"
                f"Property: {prop_name}\n"
                f"Dates: {start_date_str} to {end_date_str}\n"
                f"Price: {booking.get('total_price')} KZT\n"
                f"Status: {status_display}"
            )

            keyboard = []
            cancellable_statuses = ['pending', 'pending_payment', 'confirmed'] # Example statuses
            if booking.get('status') in cancellable_statuses:
                keyboard.append([InlineKeyboardButton("Cancel Booking", callback_data=f"cancel_booking_{booking.get('id')}")])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await update.message.reply_text(booking_info, reply_markup=reply_markup)

        if isinstance(bookings, dict) and bookings.get('count', 0) > len(results_list):
            await update.message.reply_text(f"Showing {len(results_list)} of {bookings.get('count')} bookings.")

    except requests.exceptions.HTTPError as e:
        logger.error(f"API HTTP Error fetching my_bookings for {chat_id}: {e.response.status_code if e.response else 'N/A'} - {e.response.text if e.response else str(e)}")
        if e.response and e.response.status_code == 401:
             await update.message.reply_text("Authentication failed. Please /start again.")
        else:
            await update.message.reply_text("Could not retrieve your bookings at this time.")
    except requests.exceptions.RequestException as e:
        logger.error(f"API RequestException fetching my_bookings for {chat_id}: {e}")
        await update.message.reply_text("Error connecting to the booking service.")
    except Exception as e:
        logger.error(f"Unexpected error in my_bookings_command_handler for {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("An unexpected error occurred.")


async def cancel_booking_callback_handler(update, context):
    query = update.callback_query
    await query.answer() # Acknowledge callback

    chat_id = str(query.message.chat_id)
    user_profile = UserProfile.objects.filter(telegram_chat_id=chat_id).first()
    if not user_profile or not context.user_data.get('jwt_access_token'):
        await context.bot.send_message(chat_id=chat_id, text="Error: User not authenticated. Please /start again.")
        return

    booking_id = query.data.replace("cancel_booking_", "")
    api_url = f"{settings.SITE_URL}/api/v1/bookings/{booking_id}/"

    try:
        response = requests.delete(api_url, headers={'Authorization': f'Bearer {context.user_data.get("jwt_access_token")}'})
        response.raise_for_status()

        logger.info(f"Booking ID {booking_id} cancelled successfully by user {chat_id}.")
        await query.edit_message_text(text=f"Booking ID {booking_id} has been successfully cancelled.")

    except requests.exceptions.HTTPError as e:
        error_message = f"Failed to cancel booking ID {booking_id}."
        if e.response is not None:
            if e.response.status_code == 404:
                error_message = f"Booking ID {booking_id} not found or already processed."
            elif e.response.status_code == 403:
                error_message = f"You do not have permission to cancel this booking or it cannot be cancelled now."
            else:
                try:
                    error_details = e.response.json()
                    api_errors_list = [] # Changed variable name to avoid conflict
                    if isinstance(error_details, dict):
                        for k, v_list in error_details.items(): # Changed v to v_list
                            if isinstance(v_list, list): api_errors_list.append(f"{k}: {', '.join(str(i) for i in v_list)}")
                            else: api_errors_list.append(f"{k}: {str(v_list)}") # Ensure v_list is string
                    elif isinstance(error_details, list): # Handle list of errors
                         api_errors_list = [str(item) for item in error_details]
                    else: # Handle plain text error
                        api_errors_list.append(e.response.text)

                    if api_errors_list: error_message += " Details: " + "; ".join(api_errors_list)
                    else: error_message += f" Server responded with status {e.response.status_code}."
                except json.JSONDecodeError:
                     error_message += f" Server responded with status {e.response.status_code} and non-JSON error: {e.response.text[:100]}"
        logger.error(f"API HTTPError cancelling booking {booking_id} for user {chat_id}: {e.response.text if e.response else str(e)}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=error_message)
    except requests.exceptions.RequestException as e:
        logger.error(f"API RequestException cancelling booking {booking_id} for user {chat_id}: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=f"Error connecting to the service to cancel booking {booking_id}.")
    except Exception as e:
        logger.error(f"Unexpected error in cancel_booking_callback_handler for {chat_id}, booking {booking_id}: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text=f"An unexpected error occurred while trying to cancel booking {booking_id}.")
