# booking_bot/users/migrations/0004_add_ko_factor_fields.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_userprofile_telegram_chat_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='ko_factor',
            field=models.FloatField(
                default=0,
                help_text='Процент отмененных бронирований пользователем'
            ),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='requires_prepayment',
            field=models.BooleanField(
                default=False,
                help_text='Требуется предоплата из-за высокого процента отмен'
            ),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='language',
            field=models.CharField(
                max_length=5,
                choices=[
                    ('ru', 'Русский'),
                    ('kz', 'Қазақша'),
                    ('en', 'English'),
                ],
                default='ru',
                help_text='Язык интерфейса'
            ),
        ),
    ]
