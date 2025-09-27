from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0002_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="booking",
            name="user",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="bookings",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Пользователь",
            ),
        ),
        migrations.AlterField(
            model_name="booking",
            name="cancelled_by",
            field=models.ForeignKey(
                blank=True,
                help_text="Кто отменил бронирование",
                null=True,
                on_delete=models.SET_NULL,
                related_name="cancelled_bookings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
