from django.conf import settings
from django.db import migrations, models


def ensure_user_for_profiles(apps, schema_editor):
    UserProfile = apps.get_model("users", "UserProfile")

    for profile in UserProfile.objects.filter(user__isnull=True):
        # ensure_user_exists создает пользователя и связывает профиль
        profile.ensure_user_exists()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(ensure_user_for_profiles, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userprofile",
            name="user",
            field=models.OneToOneField(
                on_delete=models.CASCADE,
                related_name="profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
