"""
REST API Views for ZIMRA Fiscal Device.

These views are thin wrappers around the public `fiscguy` library API.
The core logic resides in `fiscguy.api` and `fiscguy.services`.

For programmatic use, import directly from fiscguy:
    from fiscguy import open_day, close_day, submit_receipt, ...
"""

from loguru import logger
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from fiscguy.exceptions import (
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
from fiscguy.services.closing_day_service import ClosingDayService
from fiscguy.services.configuration_service import ConfigurationService
from fiscguy.services.open_day_service import OpenDayService
from fiscguy.services.ping_service import PingService
from fiscguy.services.receipt_service import ReceiptService
from fiscguy.services.status_service import StatusService


class ReceiptView(generics.GenericAPIView):
    """REST endpoint to list and submit receipts.

    GET: List all receipts
    POST: Create and submit a receipt to ZIMRA
    """

    serializer_class = ReceiptSerializer
    queryset = Receipt.objects.all()

    def get(self, request):
        """List receipts ordered by creation date."""
        data = self.queryset.order_by("created_at").select_related("buyer")
        return Response(ReceiptSerializer(data, many=True).data)

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
    """REST endpoint to get device configuration.

    GET: Fetch stored taxpayer configuration
    """

    def get(self, request):
        try:
            config = Configuration.objects.first()
            if not config:
                return Response({}, status=status.HTTP_200_OK)
            return Response(ConfigurationSerializer(config).data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Configuration fetch failed")
            return Response({"error": str(e)}, status=400)


class TaxView(APIView):
    """REST endpoint to list available taxes.

    GET: Fetch all configured tax types
    """

    def get(self, request):
        try:
            taxes = Taxes.objects.all()
            return Response(TaxSerializer(taxes, many=True).data, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Tax fetch failed")
            raise


class GetStatusView(APIView):
    """REST endpoint to get device and fiscal day status.

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
    """End point foor device ping"""

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

            fiscal_day = FiscalDay.objects.filter(is_open=True).first()
            if not fiscal_day:
                return Response(
                    {"error": "No open fiscal day to close"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            fiscal_counters = fiscal_day.counters.all()
            tax_map = {t.tax_id: t.name for t in Taxes.objects.all()}

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
            return Response(status=status.HTTP_200_OK)
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
