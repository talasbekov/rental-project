# Generated by Django 5.2.3 on 2025-06-13 19:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='kaspi_payment_id',
            field=models.CharField(blank=True, help_text="Kaspi's unique ID for the payment attempt", max_length=255, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('pending_payment', 'Pending Payment'), ('payment_failed', 'Payment Failed'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled'), ('completed', 'Completed')], default='pending', max_length=20),
        ),
    ]
