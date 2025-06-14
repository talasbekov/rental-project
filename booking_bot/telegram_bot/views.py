import json
import logging
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import telegram # python-telegram-bot library
from django.apps import apps # To access AppConfig

logger = logging.getLogger(__name__)

@csrf_exempt
async def telegram_webhook(request):
    bot_config = apps.get_app_config('telegram_bot') # Use the app name 'telegram_bot'
    application = bot_config.bot_application

    if not application:
        logger.error("Telegram application not initialized in AppConfig.")
        return JsonResponse({'status': 'error', 'message': 'Bot not configured'}, status=500)

    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            update = telegram.Update.de_json(data, application.bot) # Get bot instance from application

            # Dispatch the update to the PTB application
            # This is how you feed an update received externally (e.g., via Django)
            # into the python-telegram-bot processing queue.
            await application.process_update(update)

            return JsonResponse({'status': 'ok'})
        except json.JSONDecodeError:
            logger.error("Telegram webhook: Invalid JSON received.")
            return HttpResponseBadRequest('Invalid JSON')
        except Exception as e:
            logger.error(f"Error in Telegram webhook processing: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return HttpResponse("Method not allowed", status=405)
