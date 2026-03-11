from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BuyerViewset,
    CloseDayView,
    ConfigurationView,
    DevicePing,
    GetStatusView,
    OpenDayView,
    ReceiptView,
    TaxView,
)

router = DefaultRouter()
router.register(r"buyer/", BuyerViewset, basename="buyer")

app_name = "fiscguy"

urlpatterns = [
    path("get-ping/", DevicePing.as_view(), name="ping"),
    path("taxes/", TaxView.as_view(), name="taxes"),
    path("open-day/", OpenDayView.as_view(), name="open"),
    path("close-day/", CloseDayView.as_view(), name="close"),
    path("get-status/", GetStatusView.as_view(), name="status"),
    path("receipts/", ReceiptView.as_view(), name="receipts"),
    path("configuration/", ConfigurationView.as_view(), name="configuration"),
] + router.urls
