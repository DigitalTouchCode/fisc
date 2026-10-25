from django.contrib import messages
from django.contrib.auth import authenticate
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from loguru import logger

from fiscguy import audit, conf
from fiscguy.exceptions import (
    CertificateError,
    CloseDayError,
    ConfigurationError,
    DeviceRegistrationError,
    FiscalDayError,
    StatusError,
)
from fiscguy.models import AuditLog, Certs, Configuration, FiscalDay, Receipt, Taxes
from fiscguy.serializers import ReceiptSerializer
from fiscguy.services.cert_bundle import describe_certificate
from fiscguy.services.certs_service import CertificateService
from fiscguy.services.closing_day_service import ClosingDayService
from fiscguy.services.configuration_service import ConfigurationService
from fiscguy.services.device_registration_service import (
    DeviceRegistrationService,
    ResetConfirmationRequired,
)
from fiscguy.services.manual_registration_service import ManualDeviceRegistrationService
from fiscguy.services.open_day_service import OpenDayService
from fiscguy.services.ping_service import PingService
from fiscguy.services.status_service import StatusService
from fiscguy.web.forms import ApiRegistrationForm, ManualRegistrationForm, ReauthForm
from fiscguy.web.security import FiscguyWebMixin, mark_reauthenticated, throttled

PAGE_SIZE = 25


def notify(request, level, text):
    messages.add_message(request, level, text, fail_silently=True)


def get_device_or_404(request, pk):
    """Device lookup limited to what the host allows this request to see."""
    device = conf.device_queryset(request).filter(pk=pk).first()
    if device is None:
        raise Http404
    return device


def device_summary(device):
    cert = Certs.objects.filter(device=device).first()
    return {
        "device": device,
        "certificate": describe_certificate(cert.certificate) if cert else None,
        "day": FiscalDay.objects.filter(device=device).order_by("-day_no").first(),
    }


class DashboardView(FiscguyWebMixin, View):
    action = "view_receipts"

    def get(self, request):
        devices = [device_summary(d) for d in conf.device_queryset(request).order_by("device_id")]
        return render(request, "fiscguy/dashboard.html", {"devices": devices})


class DeviceDetailView(FiscguyWebMixin, View):
    action = "view_receipts"

    def get(self, request, pk):
        device = get_device_or_404(request, pk)
        context = device_summary(device)
        context.update(
            configuration=Configuration.objects.filter(device=device).first(),
            taxes=Taxes.objects.filter(device=device),
            poll_status=bool(context["day"] and context["day"].close_state == FiscalDay.CloseState.CLOSE_PENDING),
            can_close=conf.access_allowed(request, "close_day"),
            can_manage=conf.access_allowed(request, "manage_device"),
        )
        return render(request, "fiscguy/device_detail.html", context)


class DeviceStatusView(FiscguyWebMixin, View):
    """JSON used by the page to poll the fiscal day while a close request is pending."""

    action = "view_receipts"

    def get(self, request, pk):
        device = get_device_or_404(request, pk)
        if throttled(request, "status", limit=30):
            return JsonResponse({"error": "Too many requests"}, status=429)
        try:
            payload = StatusService(device).get_status()
        except StatusError as exc:
            return JsonResponse({"error": str(exc)}, status=502)
        day = FiscalDay.objects.filter(device=device).order_by("-day_no").first()
        return JsonResponse(
            {
                "fdms_status": payload.get("fiscalDayStatus"),
                "day_no": day.day_no if day else None,
                "close_state": day.close_state if day else None,
                "is_open": day.is_open if day else False,
            }
        )


class DevicePingView(FiscguyWebMixin, View):
    action = "view_receipts"

    def get(self, request, pk):
        device = get_device_or_404(request, pk)
        if throttled(request, "ping", limit=30):
            return JsonResponse({"online": False, "error": "Too many requests"}, status=429)
        try:
            PingService(device).ping()
        except Exception:
            return JsonResponse({"online": False}, status=503)
        return JsonResponse({"online": True})


class DeviceActionView(FiscguyWebMixin, View):
    """POST-only action on one device, audited, with a flash message."""

    http_method_names = ["post"]
    audit_action = ""
    success_message = ""
    expected_errors: tuple = ()

    def perform(self, request, device) -> None:
        raise NotImplementedError

    def post(self, request, pk):
        device = get_device_or_404(request, pk)
        if throttled(request, self.audit_action, limit=10):
            notify(request, messages.ERROR, "Too many attempts. Wait a minute and try again.")
            return redirect("fiscguy_web:device", pk=device.pk)
        try:
            self.perform(request, device)
        except self.expected_errors as exc:
            audit.record(request, f"{self.audit_action}_failed", device)
            notify(request, messages.ERROR, str(exc))
        except Exception:
            logger.exception(f"{self.audit_action} failed for device {device}")
            audit.record(request, f"{self.audit_action}_failed", device)
            notify(request, messages.ERROR, "Something went wrong. Check the server logs.")
        else:
            audit.record(request, self.audit_action, device)
            notify(request, messages.SUCCESS, self.success_message)
        return redirect("fiscguy_web:device", pk=device.pk)


class OpenDayView(DeviceActionView):
    action = "close_day"
    audit_action = "open_day"
    success_message = "Fiscal day opened."
    expected_errors = (FiscalDayError, ConfigurationError)

    def perform(self, request, device):
        OpenDayService(device).open_day()
        ConfigurationService(device).config()


class CloseDayView(DeviceActionView):
    action = "close_day"
    audit_action = "close_day"
    success_message = "Close request sent to FDMS."
    expected_errors = (CloseDayError, FiscalDayError)

    def perform(self, request, device):
        day = FiscalDay.objects.filter(device=device, is_open=True).first()
        if day is None:
            raise CloseDayError("There is no open fiscal day to close.")
        ClosingDayService(
            device=device,
            fiscal_day=day,
            fiscal_counters=day.counters.all(),
            tax_map={t.tax_id: t.name for t in Taxes.objects.filter(device=device)},
        ).close_day()


class SyncConfigView(DeviceActionView):
    action = "manage_device"
    audit_action = "sync_config"
    success_message = "Configuration and taxes synced."
    expected_errors = (ConfigurationError,)

    def perform(self, request, device):
        ConfigurationService(device).config()


class RenewCertificateView(DeviceActionView):
    action = "manage_device"
    require_reauth = True
    audit_action = "issue_certificate"
    success_message = "Certificate renewed."
    expected_errors = (CertificateError,)

    def perform(self, request, device):
        CertificateService(device).issue_certificate()


class ReceiptListView(FiscguyWebMixin, View):
    action = "view_receipts"

    def get(self, request, pk):
        device = get_device_or_404(request, pk)
        receipts = Receipt.objects.filter(device=device).order_by("-created_at")
        page = Paginator(receipts, PAGE_SIZE).get_page(request.GET.get("page"))
        return render(request, "fiscguy/receipts.html", {"device": device, "page": page})


class ReceiptDetailView(FiscguyWebMixin, View):
    action = "view_receipts"

    def get(self, request, pk):
        receipt = (
            conf.scope_to_devices(request, Receipt.objects.all())
            .select_related("device", "buyer")
            .prefetch_related("lines__tax_type")
            .filter(pk=pk)
            .first()
        )
        if receipt is None:
            raise Http404
        qr = ReceiptSerializer(receipt).data.get("qr_code_data", "")
        return render(request, "fiscguy/receipt_detail.html", {"receipt": receipt, "qr": qr})


class RegistrationView(FiscguyWebMixin, View):
    """Shared flow for the API and manual registration pages."""

    action = "manage_device"
    require_reauth = True
    form_class = None
    template = ""
    audit_action = ""

    def register(self, form):
        raise NotImplementedError

    def get(self, request):
        return render(request, self.template, {"form": self.form_class()})

    def post(self, request):
        form = self.form_class(request.POST, request.FILES)
        if throttled(request, self.audit_action, limit=5):
            form.add_error(None, "Too many attempts. Wait a minute and try again.")
        elif form.is_valid():
            try:
                device = self.register(form)
            except ResetConfirmationRequired as exc:
                audit.record(request, f"{self.audit_action}_reset_needed", detail=form.cleaned_data["device_id"])
                form.add_error("confirm_text", str(exc))
            except DeviceRegistrationError as exc:
                audit.record(request, f"{self.audit_action}_failed", detail=form.cleaned_data["device_id"])
                form.add_error(None, str(exc))
            else:
                audit.record(request, self.audit_action, device, "production" if device.production else "test")
                notify(request, messages.SUCCESS, f"Device {device.device_id} registered.")
                return redirect("fiscguy_web:device", pk=device.pk)
        return render(request, self.template, {"form": form})


class ApiRegistrationView(RegistrationView):
    form_class = ApiRegistrationForm
    template = "fiscguy/register.html"
    audit_action = "register_device"

    def register(self, form):
        data = form.cleaned_data
        return DeviceRegistrationService().register(
            org_name=data["org_name"],
            device_id=data["device_id"],
            activation_key=data["activation_key"],
            model_name=data["model_name"],
            model_version=data["model_version"],
            device_sn=data["device_sn"],
            production=data["production"],
            confirm_reset=form.confirm_reset(),
        )


class ManualRegistrationView(RegistrationView):
    form_class = ManualRegistrationForm
    template = "fiscguy/register_manual.html"
    audit_action = "register_device_manual"

    def register(self, form):
        data = form.cleaned_data
        result = ManualDeviceRegistrationService().register(
            org_name=data["org_name"],
            device_id=data["device_id"],
            production=data["production"],
            certificate_text=data["certificate_pem"],
            private_key_text=data["private_key_pem"],
            activation_key=data.get("activation_key", ""),
            model_name=data["model_name"],
            model_version=data["model_version"],
            device_sn=data.get("device_sn", ""),
            confirm_reset=form.confirm_reset(),
        )
        for warning in result.bundle.warnings:
            notify(self.request, messages.WARNING, warning)
        return result.device


class ReauthView(FiscguyWebMixin, View):
    action = None

    def get(self, request):
        return render(request, "fiscguy/reauth.html", {"form": ReauthForm(), "next": request.GET.get("next", "")})

    def post(self, request):
        form = ReauthForm(request.POST)
        target = request.POST.get("next", "")
        if throttled(request, "reauth", limit=5, window=300):
            form.add_error(None, "Too many attempts. Try again in a few minutes.")
        elif form.is_valid():
            user = authenticate(request, username=request.user.get_username(), password=form.cleaned_data["password"])
            if user is not None and user.pk == request.user.pk:
                mark_reauthenticated(request)
                if not url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
                    target = reverse("fiscguy_web:dashboard")
                return redirect(target)
            audit.record(request, "reauth_failed")
            form.add_error("password", "Incorrect password.")
        return render(request, "fiscguy/reauth.html", {"form": form, "next": target})


class AuditLogView(FiscguyWebMixin, View):
    action = "manage_device"

    def get(self, request):
        page = Paginator(AuditLog.objects.all(), 50).get_page(request.GET.get("page"))
        return render(request, "fiscguy/audit.html", {"page": page})
