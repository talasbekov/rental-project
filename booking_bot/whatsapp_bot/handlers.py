import json # Added for whatsapp_state
from django.contrib.auth.models import User
from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property
from booking_bot.bookings.models import Booking
from booking_bot.payments import initiate_payment as kaspi_initiate_payment, KaspiPaymentError
import logging
import requests
from .. import settings
from datetime import datetime, date, timedelta
from django.db import transaction, IntegrityError

logger = logging.getLogger(__name__)

# --- Constants for State Machine and Buttons ---
ACTION_NONE = 'none'
ACTION_MAIN_MENU = 'main_menu'
ACTION_SELECTING_REGION = 'selecting_region'
ACTION_SELECTING_ROOMS = 'selecting_rooms'
ACTION_DISPLAYING_APARTMENTS = 'displaying_apartments'
ACTION_AWAITING_APARTMENT_ID = 'awaiting_apartment_id'
ACTION_AWAITING_PAYMENT_CONFIRMATION = 'awaiting_payment_confirmation'


BUTTON_SEARCH_APARTMENTS = "Search Available Apartments"
REGIONS = ["Yesil District", "Nurinsky District", "Almaty District", "Saryarkinsky District", "Baikonursky District"]
ROOM_COUNTS = ["1", "2", "3", "4"]
BUTTON_NEXT_3 = "Next 3"
BUTTON_SELECT_ID = "Select ID"

PAGE_SIZE = 3
# --- End Constants ---

# --- State Management Helper Functions ---
def get_user_state(user_profile):
    """Retrieves and parses user_profile.whatsapp_state."""
    if user_profile.whatsapp_state:
        if isinstance(user_profile.whatsapp_state, str): # Compatibility for old string-based JSON
            try:
                state = json.loads(user_profile.whatsapp_state)
            except json.JSONDecodeError:
                state = {'action': ACTION_NONE, 'data': {}}
        elif isinstance(user_profile.whatsapp_state, dict): # Already a dict (JSONField)
            state = user_profile.whatsapp_state
        else: # Unknown type
            state = {'action': ACTION_NONE, 'data': {}}

        # Ensure essential keys exist
        if 'action' not in state:
            state['action'] = ACTION_NONE
        if 'data' not in state:
            state['data'] = {}
        return state
    return {'action': ACTION_NONE, 'data': {}}

def set_user_state(user_profile, action, data=None):
    """Updates user_profile.whatsapp_state with the new action and data."""
    state_data = data if data is not None else {}
    user_profile.whatsapp_state = {'action': action, 'data': state_data}
    user_profile.save()
    logger.debug(f"Set state for {user_profile.user.username}: action={action}, data={state_data}")

def clear_user_state(user_profile):
    """Clears user state to initial."""
    set_user_state(user_profile, ACTION_NONE, {})
    logger.debug(f"Cleared state for {user_profile.user.username}")

# --- End State Management Helper Functions ---

def get_api_url(endpoint):
    base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
    return f"{base_url}/api/v1/{endpoint}"

def parse_key_value_params(text_params, expected_keys=None): # Made expected_keys optional for flexible parsing
    params = {}
    # Simple split by space for key:value pairs. Values can have spaces if they are the last part or handled by context.
    # More robust parsing might be needed for values with spaces, e.g. using quotes or specific delimiters.
    # For now, assume simple key:value pairs separated by spaces.
    # Example: name:My Apartment class:luxury rooms:3 price:10000 desc:A very nice place with a view

    # First, try to find 'desc:' as it can contain spaces and should be last
    desc_keyword = "desc:"
    if desc_keyword in text_params:
        desc_start_index = text_params.find(desc_keyword)
        desc_value = text_params[desc_start_index + len(desc_keyword):].strip()
        params['description'] = desc_value # Store description
        text_params = text_params[:desc_start_index].strip() # Process rest of the params

    parts = text_params.split(' ')
    for part in parts:
        if ':' in part:
            key, value = part.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            if expected_keys: # If specific keys are expected
                if key in expected_keys:
                    params[key] = value
            else: # Generic parsing
                params[key] = value
    return params

def parse_search_params(text_params):
    # This one is specific for search filters
    params = {}
    parts = text_params.split(' ')
    for part in parts:
        if ':' in part:
            key, value = part.split(':', 1)
            key = key.strip().lower(); value = value.strip()
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
            if created:
                user.set_unusable_password()
                user.save()
                logger.info(f"Created User: {username}")
            # Ensure 'profile' and 'profile_created' are always defined before the if/else block
            # Also, existing_profile is only defined if the first 'if' is false.
            # Let's refine this logic.

            _profile, _profile_created = UserProfile.objects.get_or_create(user=user, defaults={'role': 'user', 'phone_number': from_number})
            # We use _profile and _profile_created to avoid confusion with the outer scope's existing_profile if that was the intention.

        if _profile_created:
            # New user, send welcome message and set initial state
            send_welcome_message(_profile, twilio_messaging_response)
            logger.info(f"Registered new user {username} and sent welcome message.")
        else:
            # This else means UserProfile.objects.get_or_create found an existing profile.
            # This should ideally align with the initial `existing_profile` check.
            # If `existing_profile` was found at the start, we wouldn't reach here.
            # This path implies `existing_profile` was None, but then `get_or_create` found one.
            # This could happen if `user` object existed but `UserProfile` didn't.
            logger.info(f"User {username} existed, profile was just created or retrieved. Sending welcome.")
            send_welcome_message(_profile, twilio_messaging_response)

    except Exception as e:
        logger.error(f"Registration Error for {from_number}: {e}", exc_info=True)
        twilio_messaging_response.message("An error occurred during registration. Please try again later.")


# --- Message Sending Helper Functions ---
def _send_message_with_buttons(twilio_messaging_response, body, button_texts):
    """Helper to format message body with numbered buttons for Twilio."""
    message_body = body
    if button_texts:
        message_body += "\n\n" # Add some space before buttons
        for i, btn_text in enumerate(button_texts, 1):
            message_body += f"{i}. {btn_text}\n"
    twilio_messaging_response.message(message_body.strip())

def send_welcome_message(user_profile, twilio_messaging_response):
    """Sends the welcome message and main menu button."""
    welcome_text = "Welcome to Daily Apartment Rentals Bot! Here you can search and book apartments. How can I help you today?"
    buttons = [BUTTON_SEARCH_APARTMENTS]
    _send_message_with_buttons(twilio_messaging_response, welcome_text, buttons)
    set_user_state(user_profile, ACTION_MAIN_MENU)

def send_region_selection(user_profile, twilio_messaging_response):
    """Sends region selection prompt and buttons."""
    prompt_text = "Please select a region:"
    _send_message_with_buttons(twilio_messaging_response, prompt_text, REGIONS)
    set_user_state(user_profile, ACTION_SELECTING_REGION)

def send_room_count_selection(user_profile, twilio_messaging_response, selected_region):
    """Sends room count selection prompt and buttons."""
    prompt_text = f"You selected {selected_region}. Now, please select the number of rooms:"
    _send_message_with_buttons(twilio_messaging_response, prompt_text, ROOM_COUNTS)
    set_user_state(user_profile, ACTION_SELECTING_ROOMS, data={'region': selected_region})

def display_available_apartments(user_profile, twilio_messaging_response, user_state):
    data = user_state['data']
    region = data.get('region')
    rooms_str = data.get('rooms')
    offset = data.get('offset', 0)

    if not region or not rooms_str:
        logger.error(f"State error: region or rooms missing for display_available_apartments for {user_profile.user.username}. Data: {data}")
        twilio_messaging_response.message("Sorry, there was an error with your search criteria. Please try again.")
        send_welcome_message(user_profile, twilio_messaging_response) # Reset
        return

    try:
        rooms = int(rooms_str)
    except ValueError:
        logger.error(f"State error: rooms ('{rooms_str}') is not a valid integer for {user_profile.user.username}.")
        twilio_messaging_response.message("Sorry, the number of rooms selected was invalid. Please try again.")
        send_welcome_message(user_profile, twilio_messaging_response) # Reset
        return

    logger.info(f"User {user_profile.user.username} searching in {region} for {rooms} rooms, offset {offset}")

    # Assuming Property model has 'region' (CharField) and 'number_of_rooms' (PositiveIntegerField)
    # And PropertyPhoto related_name is 'photos'
    # And Property 'status' is 'Свободна'
    try:
        apartments_query = Property.objects.filter(
            region=region,
            number_of_rooms=rooms,
            status='Свободна'
        ).order_by('id') # Consistent ordering for pagination

        apartments_page = list(apartments_query[offset : offset + PAGE_SIZE])
        total_matching_apartments = apartments_query.count()

    except Exception as e:
        logger.error(f"Database query error for apartments: {e}", exc_info=True)
        twilio_messaging_response.message("Sorry, an error occurred while searching for apartments. Please try again later.")
        send_welcome_message(user_profile, twilio_messaging_response)
        return

    if not apartments_page:
        if offset == 0:
            twilio_messaging_response.message("No apartments found matching your criteria. Try a different search?")
        else:
            twilio_messaging_response.message("No more apartments to show for this search.")
        send_welcome_message(user_profile, twilio_messaging_response) # Reset to main menu
        return

    reply_header = f"Available Apartments in {region} with {rooms} room(s) (Page {offset // PAGE_SIZE + 1}):\n---\n"
    twilio_messaging_response.message(reply_header)

    displayed_ids = []
    for prop in apartments_page:
        displayed_ids.append(prop.id)
        # Fetch photos (simplified)
        photos = prop.photos.all() # Removed [:3] for now, will just list URLs if many
        photo_info = "No photos available."
        if photos.exists():
            photo_info = "Photos:\n" + "\n".join([p.image_url for p in photos[:3]]) # Show up to 3 photo URLs
            if photos.count() > 3:
                photo_info += f"\n(and {photos.count() - 3} more)"

        prop_details = (
            f"ID: {prop.id}\n"
            f"Name: {prop.name}\n" # Assuming Property has a name field
            f"Area: {prop.area} m²\n"
            f"Price: {prop.price_per_day} KZT/day\n"
            f"Description: {prop.description[:100]}...\n" # Truncate long descriptions
            f"{photo_info}\n---"
        )
        twilio_messaging_response.message(prop_details)

    button_options = []
    more_available = total_matching_apartments > (offset + len(apartments_page))

    if more_available:
        button_options.append(BUTTON_NEXT_3)

    if displayed_ids: # Only show select ID if apartments were displayed
        button_options.append(BUTTON_SELECT_ID)

    if not button_options: # If no more results and nothing displayed (should be caught earlier)
        twilio_messaging_response.message("End of results.")
        send_welcome_message(user_profile, twilio_messaging_response)
    else:
        # Send a follow-up message with buttons
        _send_message_with_buttons(twilio_messaging_response, "What would you like to do next?", button_options)

    # Update state with current offset and displayed IDs
    new_data = {
        'region': region,
        'rooms': rooms_str, # Keep as string from original selection
        'offset': offset,
        'displayed_ids': displayed_ids,
        'total_matching': total_matching_apartments # Store total for better "Next 3" logic
    }
    set_user_state(user_profile, ACTION_DISPLAYING_APARTMENTS, data=new_data)

# --- End Message Sending Helper Functions ---


def handle_known_user(user_profile, incoming_message_body, twilio_messaging_response):
    logger.info(f"Msg from {user_profile.user.username} ({user_profile.role}): '{incoming_message_body}'")
    user_state = get_user_state(user_profile)
    action = user_state.get('action', ACTION_NONE)
    data = user_state.get('data', {})

    # Sanitize incoming message (especially if it's a button click with a number prefix)
    # E.g., if user types "1. Yesil District", we want "Yesil District"
    # However, if they just type "1" corresponding to a button, we need to map it back.

    # Map numeric input to button text if applicable
    # This mapping should ideally happen based on the buttons presented in the current state.
    # For now, this is a simplified example. More robust mapping would be needed.
    mapped_message_body = incoming_message_body.strip()
    if action == ACTION_MAIN_MENU and mapped_message_body == "1":
        mapped_message_body = BUTTON_SEARCH_APARTMENTS
    elif action == ACTION_SELECTING_REGION:
        try:
            choice_index = int(mapped_message_body.split('.')[0]) - 1
            if 0 <= choice_index < len(REGIONS):
                mapped_message_body = REGIONS[choice_index]
        except ValueError:
            pass # Not a numeric choice, use as is
    elif action == ACTION_SELECTING_ROOMS:
        try:
            choice_index = int(mapped_message_body.split('.')[0]) - 1
            if 0 <= choice_index < len(ROOM_COUNTS):
                mapped_message_body = ROOM_COUNTS[choice_index]
        except ValueError:
            pass # Not a numeric choice, use as is

    logger.debug(f"User: {user_profile.user.username}, State Action: {action}, Data: {data}, Incoming Msg: '{incoming_message_body}', Mapped Msg: '{mapped_message_body}'")

    # --- Button-driven flow ---
    if action == ACTION_NONE or mapped_message_body.lower() in ["hi", "hello", "start", "/start", "menu", "/menu"]:
        send_welcome_message(user_profile, twilio_messaging_response)
        return

    elif action == ACTION_MAIN_MENU:
        if mapped_message_body == BUTTON_SEARCH_APARTMENTS:
            send_region_selection(user_profile, twilio_messaging_response)
            return

    elif action == ACTION_SELECTING_REGION:
        if mapped_message_body in REGIONS:
            selected_region = mapped_message_body
            send_room_count_selection(user_profile, twilio_messaging_response, selected_region)
            return

    elif action == ACTION_SELECTING_ROOMS:
        if mapped_message_body in ROOM_COUNTS:
            selected_rooms_str = mapped_message_body
            region = data.get('region')
            if not region:
                logger.error(f"State error: region missing in ACTION_SELECTING_ROOMS for {user_profile.user.username}")
                send_welcome_message(user_profile, twilio_messaging_response)
                return

            # Initial state for displaying apartments
            initial_display_state = {'region': region, 'rooms': selected_rooms_str, 'offset': 0}
            set_user_state(user_profile, ACTION_DISPLAYING_APARTMENTS, data=initial_display_state)
            display_available_apartments(user_profile, twilio_messaging_response, get_user_state(user_profile)) # Pass the new state
            return

    elif action == ACTION_DISPLAYING_APARTMENTS:
        if mapped_message_body == BUTTON_NEXT_3:
            current_offset = data.get('offset', 0)
            total_matching = data.get('total_matching', 0)

            # Increment offset only if there are more items potentially
            if (current_offset + PAGE_SIZE) < total_matching:
                data['offset'] = current_offset + PAGE_SIZE
                set_user_state(user_profile, ACTION_DISPLAYING_APARTMENTS, data=data) # Save new offset
                display_available_apartments(user_profile, twilio_messaging_response, get_user_state(user_profile))
            else:
                # This case should ideally be handled by not showing "Next 3" if no more are available.
                # However, as a fallback:
                twilio_messaging_response.message("No more apartments to show for this search.")
                # Optionally, send back to main menu or offer other options
                send_welcome_message(user_profile, twilio_messaging_response)
            return

        elif mapped_message_body == BUTTON_SELECT_ID:
            twilio_messaging_response.message("Please type the ID of the apartment you want to select for booking.")
            # Carry over existing data (region, rooms, offset, displayed_ids) to the new state
            set_user_state(user_profile, ACTION_AWAITING_APARTMENT_ID, data=data)
            return

    elif action == ACTION_AWAITING_APARTMENT_ID:
        apartment_id_str = mapped_message_body.strip()
        displayed_ids = data.get('displayed_ids', [])

        try:
            apartment_id = int(apartment_id_str)
            if apartment_id not in displayed_ids:
                # Attempt to fetch from DB to see if it's a valid ID matching current broader search criteria (region, rooms)
                # This is a fallback if user types an ID not from the *current page* but valid for the search
                is_valid_fallback = Property.objects.filter(
                    id=apartment_id,
                    region=data.get('region'),
                    number_of_rooms=int(data.get('rooms', -1)), # Use -1 or handle error if 'rooms' is missing/invalid
                    status='Свободна'
                ).exists()
                if not is_valid_fallback:
                    twilio_messaging_response.message(f"Invalid ID: '{apartment_id_str}'. Please type one of the IDs shown or restart search.")
                    # Resend current page of apartments to make it easier for user
                    display_available_apartments(user_profile, twilio_messaging_response, user_state)
                    return

            selected_property = Property.objects.get(id=apartment_id) # Assuming ID is valid by now

            # Simplified booking: today for 1 day.
            # In a real scenario, you'd ask for dates.
            start_date_booking = date.today()
            end_date_booking = start_date_booking + timedelta(days=1)

            # Check for existing bookings for this simplified 1-day scenario
            existing_bookings = Booking.objects.filter(
                property=selected_property,
                start_date__lt=end_date_booking,
                end_date__gt=start_date_booking,
                status__in=['pending_payment', 'confirmed', 'pending'] # Consider various statuses
            )
            if existing_bookings.exists():
                twilio_messaging_response.message(f"Sorry, Apartment ID {selected_property.id} is already booked or pending for today. Please select another or try again later.")
                clear_user_state(user_profile) # Or send back to display apartments
                send_welcome_message(user_profile, twilio_messaging_response)
                return

            booking = Booking.objects.create(
                user=user_profile.user,
                property=selected_property,
                start_date=start_date_booking,
                end_date=end_date_booking,
                total_price=selected_property.price_per_day, # Assuming daily rental
                status='pending_payment'
            )

            logger.info(f"Created pending_payment booking {booking.id} for User {user_profile.user.username}, Property {selected_property.id}")

            try:
                payment_info = kaspi_initiate_payment(
                    booking_id=booking.id,
                    amount=float(booking.total_price),
                    description=f"Booking for {selected_property.name} (ID: {selected_property.id})"
                )
                if payment_info and payment_info.get('checkout_url'):
                    kaspi_id_from_service = payment_info.get('payment_id') # Or 'transactionId', adjust based on actual Kaspi response key
                    if kaspi_id_from_service:
                        booking.kaspi_payment_id = kaspi_id_from_service
                        booking.save()
                        logger.info(f"Kaspi payment ID {kaspi_id_from_service} stored for booking {booking.id}")
                    else:
                        logger.warning(f"Kaspi payment ID missing in payment_info for booking {booking.id}. Response: {payment_info}")

                    twilio_messaging_response.message(
                        f"To complete your booking for Apartment ID {selected_property.id} ({selected_property.name}), "
                        f"please use the following payment link: {payment_info['checkout_url']}"
                    )
                    set_user_state(user_profile, ACTION_AWAITING_PAYMENT_CONFIRMATION,
                                   data={'booking_id': booking.id, 'apartment_id': selected_property.id})
                else:
                    logger.error(f"Kaspi payment initiation failed for booking {booking.id}. Response: {payment_info}")
                    booking.status = 'payment_failed'
                    booking.save()
                    twilio_messaging_response.message("There was an error initiating payment (no checkout URL). Please try again later or contact support.")
                    clear_user_state(user_profile) # Reset
                    send_welcome_message(user_profile, twilio_messaging_response)
            except KaspiPaymentError as e:
                logger.error(f"KaspiPaymentError for booking {booking.id}: {e}", exc_info=True)
                booking.status = 'payment_failed'
                booking.save()
                twilio_messaging_response.message(f"Payment initiation failed: {e}. Please try again or contact support.")
                clear_user_state(user_profile)
                send_welcome_message(user_profile, twilio_messaging_response)
            except Exception as e: # Catch any other unexpected error during payment call
                logger.error(f"Generic error during kaspi_initiate_payment for booking {booking.id}: {e}", exc_info=True)
                booking.status = 'payment_failed'
                booking.save()
                twilio_messaging_response.message("An unexpected error occurred with payment processing. Please try again later.")
                clear_user_state(user_profile)
                send_welcome_message(user_profile, twilio_messaging_response)

        except ValueError: # For int(apartment_id_str)
            twilio_messaging_response.message(f"Invalid ID format: '{apartment_id_str}'. Please enter a numeric ID.")
            # Optionally resend apartment list or keep state
            display_available_apartments(user_profile, twilio_messaging_response, user_state)

        except Property.DoesNotExist:
            twilio_messaging_response.message(f"Apartment with ID {apartment_id_str} not found. Please select from the list or restart.")
            # Optionally resend apartment list or keep state
            display_available_apartments(user_profile, twilio_messaging_response, user_state)
        return

    # --- Fallback to old command parsing if no button match in current state ---
    # For now, we'll assume if it reaches here, it's an attempt at an old command or unknown.

    parts = incoming_message_body.split(' ', 1) # Use original incoming_message_body for commands
    command = parts[0].lower()
    params_text = parts[1] if len(parts) > 1 else ""

    if command == '/help':
        # (Keep help text as is, or update to reflect new button flow primarily)
        help_text = ("Main Menu: Type 'menu' or 'start'.\n"
                     "Use buttons to navigate search.\n\n"
                     "Old User Commands (may be deprecated):\n"
                     "/search [criteria] - e.g., /search rooms:2\n"
                     "/view <id> - View property\n"
                     "/book property_id:<id> from:YYYY-MM-DD to:YYYY-MM-DD\n"
                     "/mybookings - View your bookings\n"
                     "/cancel_booking <id> - Cancel booking\n"
                     "/pay <id> - Pay for booking\n")
        if user_profile.role in ['admin', 'super_admin']:
            help_text += ("\nAdmin Commands:\n"
                          "/add_property name:<name> rooms:<n> class:<class> price:<price> address:<addr> area:<area_sqm> desc:<desc>\n"
                          "/edit_property <id> [field:value ... ]\n/delete_property <id>\n/view_stats\n")
        if user_profile.role == 'super_admin':
            help_text += ("\nSuper Admin Commands:\n"
                          "/list_users [role:admin|user|super_admin]\n"
                          "/manage_user <user_id> action:<set_role|...> [value:<new_role|...>]"
                          "\n/global_stats\n")
        twilio_messaging_response.message(help_text)
        return # Important: return after handling a command

    # ... (Keep other elif command == '/search', '/view', etc. blocks as they were)
    # Make sure they also `return` after execution to prevent falling through.
    # For brevity, I'm omitting the full copy of all old commands here. Assume they are below.

    elif command == '/search':
        api_params = parse_search_params(params_text)
        try:
            response = requests.get(get_api_url('properties/'), params=api_params)
            response.raise_for_status(); properties = response.json()
            if properties:
                reply = "Found properties (old search):\n";
                for prop in properties[:5]: reply += f"\nID: {prop['id']} Name: {prop['name']} Price: {prop['price_per_day']} KZT/day\nTo view: /view {prop['id']}\n----\n"
                if len(properties) > 5: reply += f"And {len(properties) - 5} more..."
            else: reply = "No properties found (old search)."
            twilio_messaging_response.message(reply)
        except Exception as e: logger.error(f"SearchErr: {e}"); twilio_messaging_response.message("Error searching (old search).")
        return

    elif command == '/view':
        property_id_str = params_text.strip()
        if not property_id_str.isdigit(): twilio_messaging_response.message("Usage: /view <property_id>"); return
        try:
            response = requests.get(get_api_url(f'properties/{property_id_str}/'))
            response.raise_for_status(); prop = response.json()
            reply = (f"ID: {prop['id']} Name: {prop['name']} Desc: {prop['description']}\n"
                     f"Addr: {prop['address']} Rooms: {prop['number_of_rooms']}, Area: {prop['area']}m²\n"
                     f"Class: {prop['property_class']}, Price: {prop['price_per_day']} KZT/day\n"
                     f"To book: /book property_id:{prop['id']} from:YYYY-MM-DD to:YYYY-MM-DD")
            twilio_messaging_response.message(reply)
        except Exception as e: logger.error(f"ViewErr: {e}"); twilio_messaging_response.message("Error viewing.")
        return

    elif command == '/book':
        expected_keys = ['property_id', 'from', 'to']
        booking_params = parse_key_value_params(params_text, expected_keys)
        prop_id_str = booking_params.get('property_id'); start_str = booking_params.get('from'); end_str = booking_params.get('to')
        if not (prop_id_str and start_str and end_str): twilio_messaging_response.message("Usage: /book property_id:<id> from:YYYY-MM-DD to:YYYY-MM-DD"); return
        try:
            prop_id = int(prop_id_str); start_d = datetime.strptime(start_str, '%Y-%m-%d').date(); end_d = datetime.strptime(end_str, '%Y-%m-%d').date()
            if start_d < date.today(): twilio_messaging_response.message("Start date cannot be in the past."); return
            if end_d <= start_d: twilio_messaging_response.message("End date must be after start date."); return
            prop = Property.objects.get(id=prop_id)
            if Booking.objects.filter(property=prop, start_date__lt=end_d, end_date__gt=start_d, status__in=['pending', 'confirmed']).exists():
                 twilio_messaging_response.message("Property not available for these dates."); return
            duration = (end_d - start_d).days; price = duration * prop.price_per_day
            booking = Booking.objects.create(user=user_profile.user, property=prop, start_date=start_d, end_date=end_d, total_price=price, status='pending')
            twilio_messaging_response.message(f"Booking success! ID: {booking.id}. Use /pay {booking.id} to confirm.")
        except Property.DoesNotExist: twilio_messaging_response.message(f"Property ID {prop_id_str} not found.")
        except ValueError: twilio_messaging_response.message("Invalid ID or date format. Use YYYY-MM-DD.")
        except Exception as e: logger.error(f"BookErr: {e}", exc_info=True); twilio_messaging_response.message("Error booking.")
        return


    elif command == '/mybookings':
        bookings = Booking.objects.filter(user=user_profile.user).order_by('-created_at')
        if not bookings.exists(): twilio_messaging_response.message("No bookings yet."); return
        reply = "Your bookings:\n";
        for b in bookings[:5]: reply += f"\nID: {b.id} Prop: {b.property.name} Status: {b.status.capitalize()}\n"
        twilio_messaging_response.message(reply)
        return

    elif command == '/cancel_booking':
        booking_id_str = params_text.strip()
        if not booking_id_str.isdigit(): twilio_messaging_response.message("Usage: /cancel_booking <id>"); return
        try:
            booking = Booking.objects.get(id=int(booking_id_str), user=user_profile.user)
            if booking.status in ['pending', 'confirmed']: booking.status = 'cancelled'; booking.save(); twilio_messaging_response.message(f"Booking {booking.id} cancelled.")
            else: twilio_messaging_response.message(f"Booking {booking.id} cannot be cancelled (Status: {booking.status}).")
        except Booking.DoesNotExist: twilio_messaging_response.message("Booking not found or no permission.")
        except Exception as e: logger.error(f"CancelErr: {e}"); twilio_messaging_response.message("Error cancelling.")
        return

    elif command == '/pay':
        booking_id_str = params_text.strip()
        if not booking_id_str.isdigit(): twilio_messaging_response.message("Usage: /pay <id>"); return
        try:
            booking = Booking.objects.get(id=int(booking_id_str), user=user_profile.user)
            if booking.status != 'pending': twilio_messaging_response.message(f"Booking {booking.id} not pending payment."); return
            pay_info = kaspi_initiate_payment(booking.id, float(booking.total_price))
            twilio_messaging_response.message(f"Pay for booking {booking.id} at: {pay_info.get('checkout_url')}")
        except Exception as e: logger.error(f"PayErr: {e}"); twilio_messaging_response.message("Error processing payment.")
        return

    # Admin Commands
    elif command == '/add_property' and user_profile.role in ['admin', 'super_admin']:
        prop_params = parse_key_value_params(params_text)
        required_fields = ['name', 'rooms', 'class', 'price', 'address', 'area']
        missing_fields = [f for f in required_fields if f not in prop_params]

        if missing_fields:
            twilio_messaging_response.message(f"Missing fields for /add_property: {', '.join(missing_fields)}. Example: name:MyPlace rooms:3 class:economy price:5000 address:Street 1 area:50 desc:Nice place")
            return
        try:
            new_property = Property.objects.create(
                owner=user_profile.user,
                name=prop_params['name'],
                number_of_rooms=int(prop_params['rooms']),
                property_class=prop_params['class'].lower(),
                price_per_day=float(prop_params['price']),
                address=prop_params['address'],
                area=float(prop_params['area']),
                description=prop_params.get('description', ''),
            )
            logger.info(f"Admin {user_profile.user.username} added property {new_property.id}: {new_property.name}")
            twilio_messaging_response.message(f"Property '{new_property.name}' (ID: {new_property.id}) added successfully!")
        except (ValueError, IntegrityError) as e:
            logger.error(f"Admin /add_property error: {e}", exc_info=True)
            twilio_messaging_response.message(f"Error adding property: Invalid data. {str(e)}. Check class (economy, business, luxury) & numeric formats.")
        except Exception as e:
            logger.error(f"Admin /add_property general error: {e}", exc_info=True)
            twilio_messaging_response.message("An error occurred while adding the property.")
        return

    elif command == '/edit_property' and user_profile.role in ['admin', 'super_admin']:
        parts_edit = params_text.split(' ', 1) # Renamed
        if not parts_edit or not parts_edit[0].isdigit():
            twilio_messaging_response.message("Usage: /edit_property <property_id> field:value [field:value...]")
            return
        prop_id_to_edit = int(parts_edit[0])
        updates_text = parts_edit[1] if len(parts_edit) > 1 else ""
        if not updates_text:
             twilio_messaging_response.message("No updates provided. Usage: /edit_property <id> field:value")
             return

        update_params = parse_key_value_params(updates_text)

        try:
            prop_to_edit = Property.objects.get(id=prop_id_to_edit)
            if user_profile.role != 'super_admin' and prop_to_edit.owner != user_profile.user:
                twilio_messaging_response.message(f"You do not have permission to edit property ID {prop_id_to_edit}.")
                return

            allowed_fields_to_edit = ['name', 'number_of_rooms', 'property_class', 'price_per_day', 'address', 'description', 'area']
            updated_fields = []
            for field, value_update in update_params.items(): # Renamed value
                if field in allowed_fields_to_edit:
                    if field == 'number_of_rooms': setattr(prop_to_edit, field, int(value_update))
                    elif field in ['price_per_day', 'area']: setattr(prop_to_edit, field, float(value_update))
                    elif field == 'property_class': setattr(prop_to_edit, field, value_update.lower())
                    else: setattr(prop_to_edit, field, value_update)
                    updated_fields.append(field)

            if not updated_fields:
                twilio_messaging_response.message("No valid fields provided for update.")
                return

            prop_to_edit.save()
            logger.info(f"Admin {user_profile.user.username} edited property {prop_to_edit.id}. Fields: {', '.join(updated_fields)}")
            twilio_messaging_response.message(f"Property ID {prop_to_edit.id} updated. Changed: {', '.join(updated_fields)}.")
        except Property.DoesNotExist:
            twilio_messaging_response.message(f"Property with ID {prop_id_to_edit} not found.")
        except (ValueError, IntegrityError) as e:
            logger.error(f"Admin /edit_property error: {e}", exc_info=True)
            twilio_messaging_response.message(f"Error editing property: Invalid data. {str(e)}")
        except Exception as e:
            logger.error(f"Admin /edit_property general error: {e}", exc_info=True)
            twilio_messaging_response.message("An error occurred while editing property.")
        return

    elif command == '/delete_property' and user_profile.role in ['admin', 'super_admin']:
        prop_id_to_delete_str = params_text.strip()
        if not prop_id_to_delete_str.isdigit():
            twilio_messaging_response.message("Usage: /delete_property <property_id>")
            return
        try:
            prop_id_to_delete = int(prop_id_to_delete_str)
            prop_to_delete = Property.objects.get(id=prop_id_to_delete)
            if user_profile.role != 'super_admin' and prop_to_delete.owner != user_profile.user:
                twilio_messaging_response.message(f"You do not have permission to delete property ID {prop_id_to_delete}.")
                return

            prop_name = prop_to_delete.name
            prop_to_delete.delete()
            logger.info(f"Admin {user_profile.user.username} deleted property {prop_id_to_delete}: {prop_name}")
            twilio_messaging_response.message(f"Property '{prop_name}' (ID: {prop_id_to_delete}) deleted successfully.")
        except Property.DoesNotExist:
            twilio_messaging_response.message(f"Property with ID {prop_id_to_delete_str} not found.")
        except Exception as e:
            logger.error(f"Admin /delete_property error: {e}", exc_info=True)
            twilio_messaging_response.message("An error occurred while deleting the property.")
        return

    elif command == '/view_stats' and user_profile.role in ['admin', 'super_admin']:
        twilio_messaging_response.message("Admin statistics feature coming soon!")
        return

    # Super Admin Commands
    elif command == '/list_users' and user_profile.role == 'super_admin':
        filter_params = parse_key_value_params(params_text, expected_keys=['role'])
        role_filter = filter_params.get('role')

        users_query = UserProfile.objects.select_related('user').all()
        if role_filter:
            if role_filter in [choice[0] for choice in UserProfile.USER_ROLE_CHOICES]:
                users_query = users_query.filter(role=role_filter)
            else:
                twilio_messaging_response.message(f"Invalid role filter: {role_filter}. Valid roles: user, admin, super_admin.")
                return

        user_profiles_list = users_query.order_by('user__username')[:20]

        if not user_profiles_list.exists():
            reply_users = "No users found" # Renamed
            if role_filter: reply_users += f" with role '{role_filter}'."
            else: reply_users += "."
            twilio_messaging_response.message(reply_users)
            return

        reply_users = "Users list"
        if role_filter: reply_users += f" (Role: {role_filter})"
        reply_users += ":\n"
        for up in user_profiles_list:
            reply_users += f"ID: {up.user.id}, User: {up.user.username}, Role: {up.get_role_display()}, Phone: {up.phone_number or 'N/A'}\n"

        if users_query.count() > 20:
            reply_users += f"\nShowing first 20 of {users_query.count()} users."
        twilio_messaging_response.message(reply_users)
        return

    elif command == '/manage_user' and user_profile.role == 'super_admin':
        parts_manage_user = params_text.split(' ', 1) # Renamed
        if not parts_manage_user or not parts_manage_user[0].isdigit():
            twilio_messaging_response.message("Usage: /manage_user <user_id> action:<action> [value:<value>]")
            return

        target_user_id = int(parts_manage_user[0])
        action_params_text = parts_manage_user[1] if len(parts_manage_user) > 1 else ""
        action_details = parse_key_value_params(action_params_text, expected_keys=['action', 'value'])

        action_cmd = action_details.get('action') # Renamed
        value_cmd = action_details.get('value') # Renamed

        if not action_cmd:
            twilio_messaging_response.message("Action not specified. e.g., action:set_role")
            return

        try:
            target_user_to_manage = User.objects.get(id=target_user_id)
            target_user_profile_to_manage = UserProfile.objects.get(user=target_user_to_manage)

            if action_cmd == 'set_role':
                if not value_cmd or value_cmd not in [choice[0] for choice in UserProfile.USER_ROLE_CHOICES]:
                    twilio_messaging_response.message(f"Invalid or missing role value. Valid roles: user, admin, super_admin.")
                    return

                if target_user_profile_to_manage.role == 'super_admin' and target_user_profile_to_manage.user == user_profile.user and value_cmd != 'super_admin':
                    twilio_messaging_response.message("Super admins cannot change their own role from super_admin.")
                    return

                old_role = target_user_profile_to_manage.get_role_display()
                target_user_profile_to_manage.role = value_cmd
                target_user_profile_to_manage.save()
                logger.info(f"SuperAdmin {user_profile.user.username} changed role of user {target_user_to_manage.username} (ID: {target_user_id}) from {old_role} to {target_user_profile_to_manage.get_role_display()}")
                twilio_messaging_response.message(f"User {target_user_to_manage.username}'s role changed from {old_role} to {target_user_profile_to_manage.get_role_display()}.")

            else:
                twilio_messaging_response.message(f"Unknown action: {action_cmd}. Supported actions: set_role.")

        except User.DoesNotExist:
            twilio_messaging_response.message(f"User with ID {target_user_id} not found.")
        except UserProfile.DoesNotExist:
            twilio_messaging_response.message(f"UserProfile for user ID {target_user_id} not found.")
        except Exception as e:
            logger.error(f"SuperAdmin /manage_user error for user {target_user_id}: {e}", exc_info=True)
            twilio_messaging_response.message("An error occurred while managing the user.")
        return

    elif command == '/global_stats' and user_profile.role == 'super_admin':
        twilio_messaging_response.message("Global statistics feature coming soon!")
        return

    # Fallback for unknown commands if not caught by button flow logic
    is_admin_command = command in ['/add_property', '/edit_property', '/delete_property', '/view_stats']
    is_super_admin_command = command in ['/list_users', '/manage_user', '/global_stats']

    if is_admin_command and user_profile.role not in ['admin', 'super_admin']:
        twilio_messaging_response.message(f"Command '{command}' is for admin users only.")
    elif is_super_admin_command and user_profile.role != 'super_admin':
        twilio_messaging_response.message(f"Command '{command}' is for super_admin users only.")
    else:
        # If it's not a recognized command and wasn't handled by the button flow states above
        twilio_messaging_response.message(f"Sorry, I didn't understand '{incoming_message_body}'. Type 'menu' to see options or /help for old commands.")
