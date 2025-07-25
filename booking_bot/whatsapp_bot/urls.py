from django.urls import path
from .views import twilio_webhook

urlpatterns = [
    path('twilio_webhook/', twilio_webhook, name='twilio_webhook'),
]
