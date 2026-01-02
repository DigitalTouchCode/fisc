from django.urls import path

from .views import ReceiptView

app_name = "fiscguy"

urlpatterns = [path("receipts", ReceiptView.as_view(), name="receipts")]
