from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="favorite",
            name="user",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="favorites",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="guestreview",
            name="guest",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="guest_reviews_received",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="guestreview",
            name="reviewer",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="guest_reviews_given",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="property",
            name="owner",
            field=models.ForeignKey(
                limit_choices_to={"is_staff": True},
                on_delete=models.CASCADE,
                related_name="properties",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Владелец",
            ),
        ),
        migrations.AlterField(
            model_name="review",
            name="user",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="reviews",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
