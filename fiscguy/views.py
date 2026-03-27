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

# Import public library functions
from fiscguy.api import (
    close_day,
    get_configuration,
    get_ping,
    get_status,
    get_taxes,
    submit_receipt,
)
from fiscguy.exceptions import FiscalDayError
from fiscguy.models import Buyer, Device, Receipt
from fiscguy.serializers import BuyerSerializer, ReceiptSerializer
from fiscguy.services.open_day_service import OpenDayService


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
        """Create and submit a receipt.

        Calls the library's submit_receipt function which handles
        serialization, creation, generation, and submission.
        """
        try:
            receipt = submit_receipt(request.data)
            return Response(ReceiptSerializer(receipt).data, status=201)
        except Exception as e:
            logger.exception("Receipt submission failed")
            return Response({"error": str(e)}, status=400)


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
            config = get_configuration()
            return Response(config, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Configuration fetch failed")
            return Response({"error": str(e)}, status=400)


class TaxView(APIView):
    """REST endpoint to list available taxes.

    GET: Fetch all configured tax types
    """

    def get(self, request):
        try:
            taxes = get_taxes()
            return Response(taxes, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Tax fetch failed")
            return Response({"error": str(e)}, status=400)


class GetStatusView(APIView):
    """REST endpoint to get device and fiscal day status.

    GET: Fetch status from ZIMRA FDMS
    """

    def get(self, request):
        try:
            status_payload = get_status()
            return Response(status_payload, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Status fetch failed")
            return Response({"error": str(e)}, status=400)


class DevicePing(APIView):
    """End point foor device ping"""

    def get(self, request):
        try:
            response = get_ping()
            return Response(response, status=status.HTTP_200_OK)
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
            return Response({"error": "No device registered"}, status=status.HTTP_404_NOT_FOUND)

        try:
            result = OpenDayService(device).open_day()
            return Response(result, status=status.HTTP_200_OK)
        except FiscalDayError as exc:
            logger.warning(f"Failed to open fiscal day for device {device}: {exc}")
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
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
        device = Device.objects.first()
        if not device:
            return Response({"error": "No device registered"}, status=status.HTTP_404_NOT_FOUND)

        try:
            result = close_day()
            return Response(result, status=status.HTTP_200_OK)
        except FiscalDayError as exc:
            logger.warning(f"Failed to close fiscal day for device {device}: {exc}")
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception(f"Unexpected error closing fiscal day for device {device}")
            return Response(
                {"error": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
