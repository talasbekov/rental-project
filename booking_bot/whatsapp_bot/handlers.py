from django.contrib.auth.models import User
from booking_bot.users.models import UserProfile
from booking_bot.listings.models import Property
from booking_bot.bookings.models import Booking
from booking_bot.payments import initiate_payment as kaspi_initiate_payment, KaspiPaymentError
import logging
import requests
from django.conf import settings
from datetime import datetime, date, timedelta
from django.db import transaction, IntegrityError

logger = logging.getLogger(__name__)

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
            if created: user.set_unusable_password(); user.save(); logger.info(f"Created User: {username}")
            profile, profile_created = UserProfile.objects.get_or_create(user=user, defaults={'role': 'user', 'phone_number': from_number})
            if profile_created: twilio_messaging_response.message(f"Welcome! Registered as {username}. (Type /help for commands)")
            else: twilio_messaging_response.message(f"Welcome back, {username}! (Type /help for commands)") # Fallback if profile existed but wasn't caught
    except Exception as e: logger.error(f"Reg Error: {e}", exc_info=True); twilio_messaging_response.message("Error registering.")

def handle_known_user(user_profile, incoming_message_body, twilio_messaging_response):
    logger.info(f"Msg from {user_profile.user.username} ({user_profile.role}): {incoming_message_body}")
    parts = incoming_message_body.split(' ', 1)
    command = parts[0].lower()
    params_text = parts[1] if len(parts) > 1 else ""

    # Standard User Commands
    if command == '/help':
        help_text = ("User Commands:\n"
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
                          # Action "delete_user_bookings" could be added, or "view_user_bookings <user_id>"
                          "\n/global_stats\n")
        twilio_messaging_response.message(help_text)

    elif command == '/search':
        api_params = parse_search_params(params_text)
        try:
            response = requests.get(get_api_url('listings/properties/'), params=api_params)
            response.raise_for_status(); properties = response.json()
            if properties:
                reply = "Found properties:\n";
                for prop in properties[:5]: reply += f"\nID: {prop['id']} Name: {prop['name']} Price: {prop['price_per_day']} KZT/day\nTo view: /view {prop['id']}\n----\n"
                if len(properties) > 5: reply += f"And {len(properties) - 5} more..."
            else: reply = "No properties found."
            twilio_messaging_response.message(reply)
        except Exception as e: logger.error(f"SearchErr: {e}"); twilio_messaging_response.message("Error searching.")

    elif command == '/view':
        property_id_str = params_text.strip()
        if not property_id_str.isdigit(): twilio_messaging_response.message("Usage: /view <property_id>"); return
        try:
            response = requests.get(get_api_url(f'listings/properties/{property_id_str}/'))
            response.raise_for_status(); prop = response.json()
            reply = (f"ID: {prop['id']} Name: {prop['name']} Desc: {prop['description']}\n"
                     f"Addr: {prop['address']} Rooms: {prop['number_of_rooms']}, Area: {prop['area']}m²\n"
                     f"Class: {prop['property_class']}, Price: {prop['price_per_day']} KZT/day\n"
                     f"To book: /book property_id:{prop['id']} from:YYYY-MM-DD to:YYYY-MM-DD")
            twilio_messaging_response.message(reply)
        except Exception as e: logger.error(f"ViewErr: {e}"); twilio_messaging_response.message("Error viewing.")

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


    elif command == '/mybookings':
        bookings = Booking.objects.filter(user=user_profile.user).order_by('-created_at')
        if not bookings.exists(): twilio_messaging_response.message("No bookings yet."); return
        reply = "Your bookings:\n";
        for b in bookings[:5]: reply += f"\nID: {b.id} Prop: {b.property.name} Status: {b.status.capitalize()}\n"
        twilio_messaging_response.message(reply)

    elif command == '/cancel_booking':
        booking_id_str = params_text.strip()
        if not booking_id_str.isdigit(): twilio_messaging_response.message("Usage: /cancel_booking <id>"); return
        try:
            booking = Booking.objects.get(id=int(booking_id_str), user=user_profile.user)
            if booking.status in ['pending', 'confirmed']: booking.status = 'cancelled'; booking.save(); twilio_messaging_response.message(f"Booking {booking.id} cancelled.")
            else: twilio_messaging_response.message(f"Booking {booking.id} cannot be cancelled (Status: {booking.status}).")
        except Booking.DoesNotExist: twilio_messaging_response.message("Booking not found or no permission.")
        except Exception as e: logger.error(f"CancelErr: {e}"); twilio_messaging_response.message("Error cancelling.")

    elif command == '/pay':
        booking_id_str = params_text.strip()
        if not booking_id_str.isdigit(): twilio_messaging_response.message("Usage: /pay <id>"); return
        try:
            booking = Booking.objects.get(id=int(booking_id_str), user=user_profile.user)
            if booking.status != 'pending': twilio_messaging_response.message(f"Booking {booking.id} not pending payment."); return
            pay_info = kaspi_initiate_payment(booking.id, float(booking.total_price))
            twilio_messaging_response.message(f"Pay for booking {booking.id} at: {pay_info.get('checkout_url')}")
        except Exception as e: logger.error(f"PayErr: {e}"); twilio_messaging_response.message("Error processing payment.")

    # Admin Commands
    elif command == '/add_property' and user_profile.role in ['admin', 'super_admin']:
        prop_params = parse_key_value_params(params_text)
        required_fields = ['name', 'rooms', 'class', 'price', 'address', 'area'] # 'desc' is optional
        missing_fields = [f for f in required_fields if f not in prop_params]

        if missing_fields:
            twilio_messaging_response.message(f"Missing fields for /add_property: {', '.join(missing_fields)}. Example: name:MyPlace rooms:3 class:economy price:5000 address:Street 1 area:50 desc:Nice place")
            return
        try:
            new_property = Property.objects.create(
                owner=user_profile.user, # Admin user becomes owner
                name=prop_params['name'],
                number_of_rooms=int(prop_params['rooms']),
                property_class=prop_params['class'].lower(),
                price_per_day=float(prop_params['price']),
                address=prop_params['address'],
                area=float(prop_params['area']),
                description=prop_params.get('description', ''), # Use 'description' from parsing, or empty
            )
            logger.info(f"Admin {user_profile.user.username} added property {new_property.id}: {new_property.name}")
            twilio_messaging_response.message(f"Property '{new_property.name}' (ID: {new_property.id}) added successfully!")
        except (ValueError, IntegrityError) as e:
            logger.error(f"Admin /add_property error: {e}", exc_info=True)
            twilio_messaging_response.message(f"Error adding property: Invalid data. {str(e)}. Check class (economy, business, luxury) & numeric formats.")
        except Exception as e:
            logger.error(f"Admin /add_property general error: {e}", exc_info=True)
            twilio_messaging_response.message("An error occurred while adding the property.")

    elif command == '/edit_property' and user_profile.role in ['admin', 'super_admin']:
        parts = params_text.split(' ', 1)
        if not parts or not parts[0].isdigit():
            twilio_messaging_response.message("Usage: /edit_property <property_id> field:value [field:value...]")
            return
        prop_id_to_edit = int(parts[0])
        updates_text = parts[1] if len(parts) > 1 else ""
        if not updates_text:
             twilio_messaging_response.message("No updates provided. Usage: /edit_property <id> field:value")
             return

        update_params = parse_key_value_params(updates_text)

        try:
            prop_to_edit = Property.objects.get(id=prop_id_to_edit)
            # Allow super_admin to edit any, admin to edit their own
            if user_profile.role != 'super_admin' and prop_to_edit.owner != user_profile.user:
                twilio_messaging_response.message(f"You do not have permission to edit property ID {prop_id_to_edit}.")
                return

            allowed_fields_to_edit = ['name', 'number_of_rooms', 'property_class', 'price_per_day', 'address', 'description', 'area']
            updated_fields = []
            for field, value in update_params.items():
                if field in allowed_fields_to_edit:
                    if field == 'number_of_rooms': setattr(prop_to_edit, field, int(value))
                    elif field in ['price_per_day', 'area']: setattr(prop_to_edit, field, float(value))
                    elif field == 'property_class': setattr(prop_to_edit, field, value.lower())
                    else: setattr(prop_to_edit, field, value)
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
            prop_to_delete.delete() # Consider impact on existing bookings (on_delete behavior)
            logger.info(f"Admin {user_profile.user.username} deleted property {prop_id_to_delete}: {prop_name}")
            twilio_messaging_response.message(f"Property '{prop_name}' (ID: {prop_id_to_delete}) deleted successfully.")
        except Property.DoesNotExist:
            twilio_messaging_response.message(f"Property with ID {prop_id_to_delete_str} not found.")
        except Exception as e:
            logger.error(f"Admin /delete_property error: {e}", exc_info=True)
            twilio_messaging_response.message("An error occurred while deleting the property.")

    elif command == '/view_stats' and user_profile.role in ['admin', 'super_admin']:
        twilio_messaging_response.message("Admin statistics feature coming soon!")

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

        user_profiles_list = users_query.order_by('user__username')[:20] # Limit results

        if not user_profiles_list.exists():
            reply = "No users found"
            if role_filter: reply += f" with role '{role_filter}'."
            else: reply += "."
            twilio_messaging_response.message(reply)
            return

        reply = "Users list"
        if role_filter: reply += f" (Role: {role_filter})"
        reply += ":\n"
        for up in user_profiles_list: # Renamed to avoid conflict
            reply += f"ID: {up.user.id}, User: {up.user.username}, Role: {up.get_role_display()}, Phone: {up.phone_number or 'N/A'}\n"

        if users_query.count() > 20:
            reply += f"\nShowing first 20 of {users_query.count()} users."
        twilio_messaging_response.message(reply)

    elif command == '/manage_user' and user_profile.role == 'super_admin':
        parts_manage = params_text.split(' ', 1) # Renamed to avoid conflict
        if not parts_manage or not parts_manage[0].isdigit():
            twilio_messaging_response.message("Usage: /manage_user <user_id> action:<action> [value:<value>]")
            return

        target_user_id = int(parts_manage[0])
        action_params_text = parts_manage[1] if len(parts_manage) > 1 else ""
        action_details = parse_key_value_params(action_params_text, expected_keys=['action', 'value'])

        action = action_details.get('action')
        value = action_details.get('value')

        if not action:
            twilio_messaging_response.message("Action not specified. e.g., action:set_role")
            return

        try:
            target_user_to_manage = User.objects.get(id=target_user_id)
            target_user_profile_to_manage = UserProfile.objects.get(user=target_user_to_manage)

            if action == 'set_role':
                if not value or value not in [choice[0] for choice in UserProfile.USER_ROLE_CHOICES]:
                    twilio_messaging_response.message(f"Invalid or missing role value. Valid roles: user, admin, super_admin.")
                    return

                if target_user_profile_to_manage.role == 'super_admin' and target_user_profile_to_manage.user == user_profile.user and value != 'super_admin':
                    twilio_messaging_response.message("Super admins cannot change their own role from super_admin.")
                    return

                old_role = target_user_profile_to_manage.get_role_display()
                target_user_profile_to_manage.role = value
                target_user_profile_to_manage.save()
                logger.info(f"SuperAdmin {user_profile.user.username} changed role of user {target_user_to_manage.username} (ID: {target_user_id}) from {old_role} to {target_user_profile_to_manage.get_role_display()}")
                twilio_messaging_response.message(f"User {target_user_to_manage.username}'s role changed from {old_role} to {target_user_profile_to_manage.get_role_display()}.")

            else:
                twilio_messaging_response.message(f"Unknown action: {action}. Supported actions: set_role.")

        except User.DoesNotExist:
            twilio_messaging_response.message(f"User with ID {target_user_id} not found.")
        except UserProfile.DoesNotExist:
            twilio_messaging_response.message(f"UserProfile for user ID {target_user_id} not found.")
        except Exception as e:
            logger.error(f"SuperAdmin /manage_user error for user {target_user_id}: {e}", exc_info=True)
            twilio_messaging_response.message("An error occurred while managing the user.")

    elif command == '/global_stats' and user_profile.role == 'super_admin':
        twilio_messaging_response.message("Global statistics feature coming soon!")

    else:
        is_admin_command = command in ['/add_property', '/edit_property', '/delete_property', '/view_stats']
        is_super_admin_command = command in ['/list_users', '/manage_user', '/global_stats']

        if is_admin_command and user_profile.role not in ['admin', 'super_admin']:
            twilio_messaging_response.message(f"Command '{command}' is for admin users only.")
        elif is_super_admin_command and user_profile.role != 'super_admin':
            twilio_messaging_response.message(f"Command '{command}' is for super_admin users only.")
        else:
            twilio_messaging_response.message(f"I received: '{incoming_message_body}'. Not sure how to handle that yet. Try /help.")
