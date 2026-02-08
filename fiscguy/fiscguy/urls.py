from django.urls import path

from .views import (
    CloseDayView,
    ConfigurationView,
    GetStatusView,
    OpenDayView,
    ReceiptView,
    TaxView,
)

app_name = "fiscguy"

urlpatterns = [
    path("taxes/", TaxView.as_view(), name="taxes"),
    path("open-day/", OpenDayView.as_view(), name="open"),
    path("close-day/", CloseDayView.as_view(), name="close"),
    path("get-status/", GetStatusView.as_view(), name="status"),
    path("receipts/", ReceiptView.as_view(), name="receipts"),
    path("configuration/", ConfigurationView.as_view(), name="configuration"),
]
