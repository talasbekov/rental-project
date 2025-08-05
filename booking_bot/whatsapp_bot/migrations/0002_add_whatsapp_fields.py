# booking_bot/users/migrations/0002_add_whatsapp_fields.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),  # Замените на вашу последнюю миграцию
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='whatsapp_phone',
            field=models.CharField(
                blank=True, 
                help_text='Номер WhatsApp пользователя (без +)', 
                max_length=20, 
                null=True, 
                unique=True
            ),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='whatsapp_state',
            field=models.JSONField(
                blank=True, 
                default=dict, 
                help_text='Состояние WhatsApp бота для пользователя'
            ),
        ),
    ]
