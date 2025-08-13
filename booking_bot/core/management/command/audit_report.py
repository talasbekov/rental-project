from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from booking_bot.core.models import AuditLog
from django.db.models import Count


class Command(BaseCommand):
    help = "Генерация отчета по аудиту доступа"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=30, help="Количество дней для отчета"
        )
        parser.add_argument("--user", type=str, help="Фильтр по пользователю")

    def handle(self, *args, **options):
        days = options["days"]
        username = options.get("user")

        # Фильтруем логи
        start_date = timezone.now() - timedelta(days=days)
        logs = AuditLog.objects.filter(timestamp__gte=start_date)

        if username:
            logs = logs.filter(user__username=username)

        # Статистика по действиям
        action_stats = (
            logs.values("action").annotate(count=Count("id")).order_by("-count")
        )

        self.stdout.write(self.style.SUCCESS(f"\n📊 Отчет по аудиту за {days} дней\n"))
        self.stdout.write(f"Всего записей: {logs.count()}\n")

        self.stdout.write("\n📈 Статистика по действиям:")
        for stat in action_stats:
            self.stdout.write(f"  {stat['action']}: {stat['count']}")

        # Топ пользователей по активности
        user_stats = (
            logs.values("user__username")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        self.stdout.write("\n👥 Топ-10 пользователей:")
        for stat in user_stats:
            self.stdout.write(f"  {stat['user__username']}: {stat['count']} действий")

        # Подозрительная активность
        suspicious = (
            logs.filter(action__in=["view_code", "send_code", "export_data"])
            .values("user__username")
            .annotate(count=Count("id"))
            .filter(count__gt=50)
            .order_by("-count")
        )

        if suspicious:
            self.stdout.write(self.style.WARNING("\n⚠️ Подозрительная активность:"))
            for stat in suspicious:
                self.stdout.write(
                    f"  {stat['user__username']}: {stat['count']} доступов к конфиденциальным данным"
                )
