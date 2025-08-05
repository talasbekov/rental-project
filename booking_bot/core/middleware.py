class AuditMiddleware:
    """Middleware для автоматического логирования доступа к конфиденциальным данным"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Сохраняем информацию о запросе для последующего использования
        if hasattr(request, 'user') and request.user.is_authenticated:
            # Добавляем пользователя к объектам Property для логирования
            from booking_bot.listings.models import Property
            Property._accessing_user = request.user

        response = self.get_response(request)

        # Очищаем временную информацию
        if hasattr(Property, '_accessing_user'):
            delattr(Property, '_accessing_user')

        return response