from loguru import logger
from rest_framework import generics, status
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from fiscguy.exceptions import (
    CertificateError,
    CloseDayError,
    ConfigurationError,
    DevicePingError,
    FiscalDayError,
    ReceiptSubmissionError,
    StatusError,
)
from fiscguy.models import Buyer, Configuration, Device, FiscalDay, Receipt, Taxes
from fiscguy.serializers import (
    BuyerSerializer,
    ConfigurationSerializer,
    ReceiptSerializer,
    TaxSerializer,
)
from fiscguy.services.certs_service import CertificateService
from fiscguy.services.closing_day_service import ClosingDayService
from fiscguy.services.configuration_service import ConfigurationService
from fiscguy.services.open_day_service import OpenDayService
from fiscguy.services.ping_service import PingService
from fiscguy.services.receipt_service import ReceiptService
from fiscguy.services.status_service import StatusService


class ReceiptCursorPagination(CursorPagination):
    """
    Cursor-based pagination for receipts.
    Provides efficient pagination for large result sets.
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "-created_at"


class ReceiptView(APIView):
    """REST endpoint to list and submit receipts.

    GET: List all receipts with cursor pagination
    POST: Create and submit a receipt to ZIMRA
    """

    serializer_class = ReceiptSerializer
    queryset = Receipt.objects.all()
    pagination_class = ReceiptCursorPagination

    def get(self, request):
        """List receipts with cursor pagination, including receipt lines."""
        queryset = (
            self.queryset.select_related("buyer").prefetch_related("lines").order_by("-created_at")
        )

        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        serializer = ReceiptSerializer(paginated_queryset, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        device = Device.objects.first()

        try:
            receipt, submission_res = ReceiptService(device).create_and_submit_receipt(request.data)
            return Response(
                ReceiptSerializer(receipt).data,
                status=status.HTTP_201_CREATED,
            )
        except ReceiptSubmissionError as exc:
            logger.error(f"Receipt submission failed for device {device}: {exc}")
            return Response(
                {"error": str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except Exception:
            logger.exception("Unexpected error during receipt submission")
            return Response(
                {"error": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ReceiptDetailView(generics.RetrieveAPIView):
    """REST endpoint to retrieve a single receipt by ID."""

    queryset = Receipt.objects.all().select_related("receipt_lines", "buyer")
    serializer_class = ReceiptSerializer
    lookup_field = "id"


class BuyerViewset(ModelViewSet):
    """Buyer crud endpoint"""

    queryset = Buyer.objects.all()
    serializer_class = BuyerSerializer


class ConfigurationView(APIView):
    """
    REST endpoint to get device configuration.
    GET: Fetch stored taxpayer configuration
    """

    def get(self, request):
        try:
            device = Device.objects.first()
            if not device:
                return Response({}, status=status.HTTP_200_OK)
            config = Configuration.objects.filter(device=device).first()
            if not config:
                return Response({}, status=status.HTTP_200_OK)
            return Response(ConfigurationSerializer(config).data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Configuration fetch failed")
            return Response({"error": str(e)}, status=400)


class TaxView(APIView):
    """
    REST endpoint to list available taxes.
    GET: Fetch all configured tax types
    """

    def get(self, request):
        try:
            device = Device.objects.first()
            if not device:
                return Response([], status=status.HTTP_200_OK)
            taxes = Taxes.objects.filter(device=device)
            return Response(TaxSerializer(taxes, many=True).data, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Tax fetch failed")
            raise


class GetStatusView(APIView):
    """
    REST endpoint to get device and fiscal day status.
    GET: Fetch status from ZIMRA FDMS
    """

    def get(self, request):
        device = Device.objects.first()
        if not device:
            return Response(
                {"error": "No device registered"},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            status_payload = StatusService(device).get_status()
            return Response(status_payload, status=status.HTTP_200_OK)
        except StatusError as e:
            logger.exception("Status fetch failed")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.exception("Status fetch failed")
            return Response({"error": str(e)}, status=400)


class DevicePing(APIView):
    """
    End point for device ping
    POST: Ping the device to check/report connectivity with ZIMRA FDMS
    """

    def post(self, request):
        device = Device.objects.first()
        if not device:
            return Response(
                {"error": "No device registered"},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            response = PingService(device).ping()
            return Response(response, status=status.HTTP_200_OK)
        except DevicePingError as e:
            logger.exception("Ping failed")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.exception("Ping failed")
            return Response({"error": str(e)}, status=400)


class OpenDayView(APIView):
    """
    POST: Open a new fiscal day for the registered device.
    """

    def post(self, request):
        device = Device.objects.first()
        if not device:
            return Response(
                {"error": "No device registered"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            result = OpenDayService(device).open_day()
            ConfigurationService(device).config()
            return Response(result, status=status.HTTP_200_OK)

        except FiscalDayError as exc:
            logger.warning(f"Failed to open fiscal day for device {device}: {exc}")
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except ConfigurationError as exc:
            logger.exception(
                f"Config sync failed after opening fiscal day for device {device}: {exc}"
            )
            return Response(
                {"error": "Fiscal day opened but configuration sync failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        except Exception as exc:
            logger.exception(f"Unexpected error opening fiscal day for device {device}")
            return Response(
                {"error": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CloseDayView(APIView):
    """
    POST: Close the open fiscal day (build counters, sign, submit).
    """

    def post(self, request):
        try:
            device = Device.objects.first()
            if not device:
                return Response(
                    {"error": "No device registered"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            fiscal_day = FiscalDay.objects.filter(device=device, is_open=True).first()
            if not fiscal_day:
                try:
                    StatusService(device).get_status()
                except StatusError:
                    logger.warning(
                        f"Could not reconcile fiscal day status with FDMS for device {device}"
                    )
                fiscal_day = FiscalDay.objects.filter(device=device, is_open=True).first()
                if not fiscal_day:
                    return Response(
                        {"error": "No open fiscal day to close"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            fiscal_counters = fiscal_day.counters.all()
            tax_map = {t.tax_id: t.name for t in Taxes.objects.filter(device=device)}

            res = ClosingDayService(
                device=device,
                fiscal_day=fiscal_day,
                fiscal_counters=fiscal_counters,
                tax_map=tax_map,
            ).close_day()

            return Response(res)
        except CloseDayError as exc:
            logger.error(f"Close day failed: {exc}")
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception:
            logger.exception("Unexpected error during close day")
            return Response(
                {"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SyncConfigurationView(APIView):
    """
    POST: Manually sync configuration from ZIMRA FDMS to local database.
    """

    def post(self, request):
        device = Device.objects.first()
        if not device:
            return Response({"error": "No device registered"}, status=status.HTTP_404_NOT_FOUND)

        try:
            ConfigurationService(device).config()
            return Response({"message": "Configuration Synced"}, status=status.HTTP_200_OK)
        except ConfigurationError as exc:
            logger.exception(f"Manual configuration sync failed: {device} : {exc}")
            return Response(
                {"error": "Manual configuration sync failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as exc:
            logger.exception(f"Unexpected error syncing configuration {device}")
            return Response(
                {"error": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class IssueCertificateView(APIView):
    """
    POST: Certificate Renewal if cert is expired
    """

    def post(self, request):
        device = Device.objects.first()
        if not device:
            return Response({"error": "No device registered"}, status=status.HTTP_404_NOT_FOUND)
        try:
            CertificateService(device).issue_certificate()
            return Response(
                {"message": "Certificate issued successfully"}, status=status.HTTP_200_OK
            )
        except CertificateError as exc:
            logger.exception(f"Certificate renewal issuance failed for device {device}: {exc}")
            return Response(
                {"error": "Certificate renewal issuance failed."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except Exception as exc:
            logger.exception(
                f"Unexpected error during certificate renewal for device {device}: {exc}"
            )
            return Response(
                {"error": "An unexpected error occurred during certificate renewal."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
