from django.contrib.auth.models import User
from booking_bot.users.models import UserProfile
# from .utils import send_whatsapp_reply (utils.py has send_whatsapp_message)
import logging
import requests # For making API calls
from django.conf import settings # To get own API base URL

logger = logging.getLogger(__name__)

# Utility to construct API URL
def get_api_url(endpoint):
    # Assuming development server for now. This should be configurable.
    # SITE_URL could be defined in settings for this.
    base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
    return f"{base_url}/api/v1/{endpoint}"


def parse_search_params(text_params):
    """ Parses params like 'rooms:2 area:50-70 class:business' into a dict for requests. """
    params = {}
    parts = text_params.split(' ')
    for part in parts:
        if ':' in part:
            key, value = part.split(':', 1)
            key = key.strip().lower()
            value = value.strip()

            if key == 'rooms':
                params['number_of_rooms'] = value
            elif key == 'class':
                params['property_class'] = value
            elif key == 'area':
                if '-' in value:
                    min_val, max_val = value.split('-', 1)
                    params['area_min'] = min_val
                    params['area_max'] = max_val
                else: # Assuming it's a minimum if only one value
                    params['area_min'] = value
            # Add more supported keys like 'sort:price_per_day'
            elif key == 'sort':
                params['ordering'] = value
    return params

def handle_unknown_user(from_number, incoming_message_body, twilio_messaging_response):
    logger.info(f"New user from {from_number}. Initiating registration.")
    existing_profile = UserProfile.objects.filter(phone_number=from_number).first()
    if existing_profile:
        logger.warning(f"User profile for {from_number} exists but user was not found by webhook. Linking to user: {existing_profile.user.username}")
        twilio_messaging_response.message(f"Welcome back, {existing_profile.user.username}! How can I help you today? (Type /help for commands)")
        return

    username = f"user_{from_number.replace('+', '')}"
    try:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'first_name': 'WhatsApp User'}
        )
        if created:
            user.set_unusable_password()
            user.save()
            logger.info(f"Created new User: {username}")

        profile, profile_created = UserProfile.objects.get_or_create(
            user=user,
            defaults={'role': 'user', 'phone_number': from_number}
        )
        if profile_created:
            twilio_messaging_response.message(f"Welcome! You've been registered as {username}. How can I help you? (Type /help for commands)")
        elif profile.phone_number != from_number:
            profile.phone_number = from_number
            profile.save()
            twilio_messaging_response.message(f"Welcome back, {username}! Your phone number has been updated. (Type /help for commands)")
        else:
             twilio_messaging_response.message(f"Welcome back, {username}! How can I help you today? (Type /help for commands)")
    except Exception as e:
        logger.error(f"Error during auto-registration for {from_number}: {e}")
        twilio_messaging_response.message("Sorry, there was an error registering you. Please try again later.")

def handle_known_user(user_profile, incoming_message_body, twilio_messaging_response):
    logger.info(f"Message from known user {user_profile.user.username} ({user_profile.role}): {incoming_message_body}")
    parts = incoming_message_body.split(' ', 1)
    command = parts[0].lower()
    params_text = parts[1] if len(parts) > 1 else ""

    if command == '/help':
        help_text = ("Available commands:\n"
                     "/search [criteria] - e.g., /search rooms:2 class:luxury area:100-150 sort:price_per_day\n"
                     "/view <property_id> - View property details\n"
                     "/book <property_id> [dates] - Book a property\n"
                     "/mybookings - View your bookings\n")
        if user_profile.role in ['admin', 'super_admin']:
            help_text += "/add_property [details] - Add a new property\n"
        twilio_messaging_response.message(help_text)

    elif command == '/search':
        api_params = parse_search_params(params_text)
        logger.info(f"Searching properties with API params: {api_params}")
        try:
            response = requests.get(get_api_url('listings/properties/'), params=api_params)
            response.raise_for_status() # Raise an exception for HTTP errors
            properties = response.json()

            if properties:
                reply = "Found properties:\n"
                for prop in properties[:5]: # Limit to 5 results for brevity
                    reply += f"\nID: {prop['id']}\nName: {prop['name']}\nRooms: {prop['number_of_rooms']}, Class: {prop['property_class']}, Area: {prop['area']}m²\nPrice: {prop['price_per_day']} KZT/day\nTo view details: /view {prop['id']}\n----\n"
                if len(properties) > 5:
                    reply += f"And {len(properties) - 5} more..."
            else:
                reply = "No properties found matching your criteria."
            twilio_messaging_response.message(reply)
        except requests.exceptions.RequestException as e:
            logger.error(f"API call to /properties/ failed: {e}")
            twilio_messaging_response.message("Sorry, I couldn't fetch property listings at the moment.")
        except Exception as e:
            logger.error(f"Error processing search results: {e}")
            twilio_messaging_response.message("Sorry, an error occurred while searching.")

    elif command == '/view':
        property_id = params_text.strip()
        if not property_id.isdigit():
            twilio_messaging_response.message("Please provide a valid property ID. Usage: /view <property_id>")
            return

        logger.info(f"Viewing property with ID: {property_id}")
        try:
            response = requests.get(get_api_url(f'listings/properties/{property_id}/'))
            response.raise_for_status()
            prop = response.json()

            reply = (f"Property Details (ID: {prop['id']}):\n"
                     f"Name: {prop['name']}\n"
                     f"Description: {prop['description']}\n"
                     f"Address: {prop['address']}\n"
                     f"Rooms: {prop['number_of_rooms']}\n"
                     f"Area: {prop['area']} m²\n"
                     f"Class: {prop['property_class']}\n"
                     f"Price: {prop['price_per_day']} KZT/day\n"
                     # Owner info might be sensitive, decide if to show: f"Owner: {prop['owner']}\n"
                     f"Added on: {prop['created_at']}\n"
                     f"To book: /book {prop['id']} from:YYYY-MM-DD to:YYYY-MM-DD")
            # If images were supported and model had image field:
            # if prop.get('image_url'):
            #    twilio_messaging_response.message(body=reply, media_url=prop['image_url'])
            # else:
            #    twilio_messaging_response.message(reply)
            twilio_messaging_response.message(reply)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                twilio_messaging_response.message(f"Sorry, property with ID {property_id} not found.")
            else:
                logger.error(f"API call to /properties/{property_id}/ failed: {e}")
                twilio_messaging_response.message("Sorry, I couldn't fetch property details.")
        except requests.exceptions.RequestException as e:
            logger.error(f"API call to /properties/{property_id}/ failed: {e}")
            twilio_messaging_response.message("Sorry, I couldn't fetch property details.")
        except Exception as e:
            logger.error(f"Error processing view property: {e}")
            twilio_messaging_response.message("Sorry, an error occurred while viewing property details.")

    elif command == '/book':
        twilio_messaging_response.message("Booking feature coming soon! Example: /book property_id:123 from:YYYY-MM-DD to:YYYY-MM-DD")
    elif command == '/mybookings':
        twilio_messaging_response.message("You'll be able to see your bookings here soon!")
    elif command == '/add_property' and user_profile.role in ['admin', 'super_admin']:
        twilio_messaging_response.message("Admin: Property addition feature coming soon!")
    else:
        twilio_messaging_response.message(f"I received: '{incoming_message_body}'. Not sure how to handle that yet. Try /help.")
