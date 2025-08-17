# Создайте файл: booking_bot/users/management/commands/fix_user_profiles.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from booking_bot.users.models import UserProfile

User = get_user_model()


class Command(BaseCommand):
    help = 'Исправляет профили пользователей без связанного User объекта'

    def handle(self, *args, **options):
        # Находим профили без пользователя
        profiles_without_user = UserProfile.objects.filter(user__isnull=True)

        self.stdout.write(
            f"Найдено {profiles_without_user.count()} профилей без пользователя"
        )

        fixed_count = 0

        for profile in profiles_without_user:
            if profile.telegram_chat_id:
                username = f"telegram_{profile.telegram_chat_id}"

                # Создаем или находим пользователя
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "first_name": "",
                        "last_name": "",
                    }
                )

                if created:
                    user.set_unusable_password()
                    user.save()
                    self.stdout.write(f"Создан пользователь: {username}")

                # Привязываем пользователя к профилю
                profile.user = user
                profile.save()

                fixed_count += 1
                self.stdout.write(f"Исправлен профиль {profile.id}")
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Профиль {profile.id} не имеет telegram_chat_id, пропускаем"
                    )
                )

        # Проверяем обязательные поля
        profiles_to_fix = UserProfile.objects.filter(
            models.Q(requires_prepayment__isnull=True) |
            models.Q(ko_factor__isnull=True) |
            models.Q(telegram_state__isnull=True) |
            models.Q(whatsapp_state__isnull=True)
        )

        if profiles_to_fix.exists():
            self.stdout.write(f"Исправляем {profiles_to_fix.count()} профилей с пустыми полями")

            for profile in profiles_to_fix:
                if profile.requires_prepayment is None:
                    profile.requires_prepayment = False
                if profile.ko_factor is None:
                    profile.ko_factor = 0.0
                if profile.telegram_state is None:
                    profile.telegram_state = {}
                if profile.whatsapp_state is None:
                    profile.whatsapp_state = {}
                profile.save()
                fixed_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Успешно исправлено {fixed_count} профилей")
        )
