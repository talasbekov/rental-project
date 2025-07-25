## Agent Instructions for ЖильеGO Telegram Bot

This document provides instructions and conventions for AI agents working on the ЖильеGO Telegram Bot codebase.

### Project Overview

ЖильеGO is a Telegram bot for daily apartment rentals. It allows users to search and book apartments, administrators to manage listings, and superusers to oversee the system and access analytics. The backend is built with Django, and the bot interacts with it via API calls.

### Development Conventions

1.  **Code Style:**
    *   Follow PEP 8 for Python code.
    *   Keep lines under 100 characters where feasible.
    *   Use clear and descriptive names for variables, functions, and classes.
2.  **Telegram Handlers:**
    *   Bot command handlers are primarily located in `booking_bot/telegram_bot/handlers.py` and `booking_bot/telegram_bot/admin_handlers.py`.
    *   Callback query handlers are centralized in `callback_query_handler` in `handlers.py`.
    *   Maintain clear separation of concerns: user-facing logic in `handlers.py`, admin-specific logic in `admin_handlers.py`.
    *   Use the `UserProfile` model (`booking_bot.users.models.UserProfile`) to manage user data and roles (`profile.role`).
    *   State management for conversations is handled using `profile.telegram_state`, a JSON field. Define states clearly (e.g., `STATE_SELECT_CITY`).
3.  **API Interaction:**
    *   The bot communicates with the Django backend via a REST API. The base URL is configured in `settings.API_BASE`.
    *   User authentication is handled via JWT tokens, typically stored in `profile.telegram_state['jwt_access_token']`. The `_get_profile` function in `handlers.py` manages token retrieval/refresh.
4.  **Settings:**
    *   Telegram Bot Token is stored in `settings.TELEGRAM_BOT_TOKEN`.
    *   Other critical settings are in `booking_bot/settings.py`.
5.  **Logging:**
    *   Use the standard Python `logging` module. Logger instances are generally set up per module.
    *   Log important events, errors, and API interactions.
6.  **Dependencies:**
    *   Project dependencies are managed in `requirements.txt`.
7.  **Testing:**
    *   While not explicitly requested for every change, aim to write tests for new complex logic. (Test infrastructure might need to be reviewed/enhanced).
8.  **Commits:**
    *   Write clear and concise commit messages.
    *   Reference the issue or task if applicable.

### Key Files and Directories

*   `booking_bot/telegram_bot/main.py`: Bot application setup, registration of handlers.
*   `booking_bot/telegram_bot/handlers.py`: Main handlers for user interactions.
*   `booking_bot/telegram_bot/admin_handlers.py`: Handlers for admin-specific functionality.
*   `booking_bot/telegram_bot/utils.py`: Utility functions for Telegram communication.
*   `booking_bot/users/models.py`: Contains `UserProfile` model.
*   `booking_bot/listings/models.py`: Contains models for `Property`, `City`, `District`, etc.
*   `booking_bot/bookings/models.py`: Contains `Booking` model.
*   `requirements.txt`: Project dependencies.
*   `manage.py`: Django management script.

### Workflow for Modifying Bot Behavior

1.  **Understand the Request:** Clarify any ambiguities.
2.  **Identify Affected Components:** Determine which handlers, models, or utility functions need changes.
3.  **Update Handlers:**
    *   For new commands, add a new `CommandHandler` in `main.py` and its corresponding function in `handlers.py` or `admin_handlers.py`.
    *   For new inline button interactions, add a new `callback_data` pattern and handle it in `callback_query_handler`.
    *   For conversation flows, manage states using `profile.telegram_state` and `MessageHandler` or further `CallbackQueryHandler` logic.
4.  **Update Models (if necessary):** If schema changes are needed, modify Django models and create/run migrations.
5.  **API Calls:** If new backend interactions are needed, ensure the API endpoints exist or are planned. Use `requests` library for API calls.
6.  **User Experience:** Ensure messages are clear, and keyboards are intuitive.
7.  **Consider Roles:** Implement logic that respects user roles (user, admin, super_admin) as defined in `UserProfile.role`.

### Important Notes

*   The bot uses `python-telegram-bot` library. Refer to its documentation for library-specific features.
*   The project is already established. Familiarize yourself with existing patterns before adding new ones.
*   Always check `settings.TELEGRAM_BOT_TOKEN` and `settings.API_BASE` configurations when troubleshooting connection issues.
*   The `_get_profile` function is crucial for user identification and session management.

This document is a living guide. Please update it if you establish new conventions or discover important information for future agent interactions.
