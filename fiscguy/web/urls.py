from django.urls import path

from fiscguy.web import views

app_name = "fiscguy_web"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("reauth/", views.ReauthView.as_view(), name="reauth"),
    path("audit/", views.AuditLogView.as_view(), name="audit"),
    path("devices/register/", views.ApiRegistrationView.as_view(), name="register"),
    path("devices/register/manual/", views.ManualRegistrationView.as_view(), name="register-manual"),
    path("devices/<int:pk>/", views.DeviceDetailView.as_view(), name="device"),
    path("devices/<int:pk>/status/", views.DeviceStatusView.as_view(), name="status"),
    path("devices/<int:pk>/ping/", views.DevicePingView.as_view(), name="ping"),
    path("devices/<int:pk>/open-day/", views.OpenDayView.as_view(), name="open-day"),
    path("devices/<int:pk>/close-day/", views.CloseDayView.as_view(), name="close-day"),
    path("devices/<int:pk>/sync-config/", views.SyncConfigView.as_view(), name="sync-config"),
    path("devices/<int:pk>/renew-certificate/", views.RenewCertificateView.as_view(), name="renew-certificate"),
    path("devices/<int:pk>/receipts/", views.ReceiptListView.as_view(), name="receipts"),
    path("receipts/<int:pk>/", views.ReceiptDetailView.as_view(), name="receipt"),
]
