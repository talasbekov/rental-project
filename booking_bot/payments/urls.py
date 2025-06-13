from django.urls import path, include
from rest_framework.routers import DefaultRouter
# Remove PaymentViewSet if it's not defined or not used, or ensure it's correctly implemented.
# For now, I'll assume it might exist for other purposes, or was a placeholder.
# from .views import PaymentViewSet
from .views import kaspi_payment_webhook # Import the new webhook view

# router = DefaultRouter()
# router.register(r'payments', PaymentViewSet) # Comment out if PaymentViewSet is not ready/used

urlpatterns = [
    # path('', include(router.urls)), # Comment out if router is not used
    path('kaspi-webhook/', kaspi_payment_webhook, name='kaspi_payment_webhook'),
]

# If you still need the PaymentViewSet, ensure it's defined in views.py
# and uncomment the router lines. If not, this simplified urlpatterns is fine.
# For example, if PaymentViewSet is defined:
# from .views import PaymentViewSet, kaspi_payment_webhook
# router = DefaultRouter()
# router.register(r'payments', PaymentViewSet)
# urlpatterns = [
#     path('', include(router.urls)),
#     path('kaspi-webhook/', kaspi_payment_webhook, name='kaspi_payment_webhook'),
# ]
