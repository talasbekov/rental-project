from django.urls import path
from .views import whatsapp_webhook, whatsapp_verify_webhook

urlpatterns = [
    path('webhook/', whatsapp_webhook, name='whatsapp_webhook'),
    path('webhook/verify/', whatsapp_verify_webhook, name='whatsapp_verify_webhook'),
]