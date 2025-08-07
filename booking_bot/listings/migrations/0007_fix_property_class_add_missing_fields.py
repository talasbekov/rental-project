# booking_bot/listings/migrations/0007_fix_property_class_add_missing_fields.py

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('listings', '0006_alter_propertyphoto_options_and_more'),
    ]

    operations = [
        # Изменяем значение economy на comfort
        migrations.RunSQL(
            "UPDATE listings_property SET property_class = 'comfort' WHERE property_class = 'economy';",
            reverse_sql="UPDATE listings_property SET property_class = 'economy' WHERE property_class = 'comfort';"
        ),

        # Обновляем choices для property_class
        migrations.AlterField(
            model_name='property',
            name='property_class',
            field=models.CharField(
                choices=[
                    ('comfort', 'Комфорт'),
                    ('business', 'Бизнес'),
                    ('premium', 'Премиум')
                ],
                default='comfort',
                max_length=20
            ),
        ),

        # Добавляем недостающие поля
        migrations.AddField(
            model_name='property',
            name='entry_floor',
            field=models.IntegerField(
                null=True,
                blank=True,
                help_text='Этаж квартиры'
            ),
        ),

        migrations.AddField(
            model_name='property',
            name='entry_code',
            field=models.CharField(
                max_length=50,
                null=True,
                blank=True,
                help_text='Код домофона'
            ),
        ),

        migrations.AddField(
            model_name='property',
            name='owner_phone',
            field=models.CharField(
                max_length=20,
                null=True,
                blank=True,
                help_text='Телефон владельца/риелтора'
            ),
        ),

        # Добавляем зашифрованные версии новых полей
        migrations.AddField(
            model_name='property',
            name='_encrypted_entry_code',
            field=models.TextField(
                db_column='encrypted_entry_code',
                blank=True,
                default=''
            ),
        ),

        migrations.AddField(
            model_name='property',
            name='_encrypted_owner_phone',
            field=models.TextField(
                db_column='encrypted_owner_phone',
                blank=True,
                default=''
            ),
        ),
    ]
