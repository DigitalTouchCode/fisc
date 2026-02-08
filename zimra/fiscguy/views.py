from django.shortcuts import render
from easy_pagination import NoPagination, StandardPagination
from loguru import logger
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from fiscguy.models import Configuration, Device, FiscalDay, Receipt, Taxes
from fiscguy.serializers import (
    ConfigurationSerializer,
    ReceiptSerializer,
    TaxSerializer,
)
from fiscguy.zimra_base import ZIMRAClient
from fiscguy.zimra_receipt_handler import ZIMRAReceiptHandler
from fiscguy.services.closing_day_service import ClosingDayService
from fiscguy.services.receipt_service import ReceiptService
from fiscguy.services.configuration_service import create_or_update_config


client = ZIMRAClient(Device.objects.first())
receipt_handler = ZIMRAReceiptHandler()


class ReceiptView(generics.GenericAPIView):
    """view to submit receipt"""

    serializer_class = ReceiptSerializer
    queryset = Receipt.objects.all()

    def get(self, request):
        data = self.queryset.order_by("created_at").select_related("buyer")
        return Response(data)

    def post(self, request):
        service = ReceiptService(receipt_handler=receipt_handler)
        try:
            receipt, submission_res = service.create_and_submit_receipt(request.data)
        except Exception as e:
            logger.exception("Receipt creation failed")
            return Response({"error": str(e)}, status=400)

        logger.info(f"Receipt submitted to ZIMRA: {submission_res}")
        return Response(ReceiptSerializer(receipt).data, status=201)


class ReceiptDetailView(generics.RetrieveAPIView):
    queryset = Receipt.objects.all().select_related("receipt_lines", "buyer")
    serializer_class = ReceiptSerializer
    lookup_field = "id"


class ConfigurationView(APIView):
    """
    ZIMRA FDMS Configuration View
    """

    serializer_class = ConfigurationSerializer

    def get(self, request):
        config = Configuration.objects.first()
        return Response(self.serializer_class(config).data, status=status.HTTP_200_OK)


class TaxView(APIView):
    """
    Return the list of taxes.
    """

    serializer_class = TaxSerializer

    def get(self, request):
        taxes = Taxes.objects.all()
        logger.info(taxes.values())
        return Response(
            self.serializer_class(taxes, many=True).data,
            status=status.HTTP_200_OK,
        )


class GetStatusView(APIView):
    """
    Shows the fiscal day status either open or closed(with errors or not)
    """

    def get(self, request):
        res = client.get_status()
        return Response(res, status=status.HTTP_200_OK)


class OpenDayView(APIView):
    """
    View to open a fiscal day
    """

    def get(self, request):
        # config_res = client.get_config()
        # create_or_update_config(config_res)

        res = client.open_day()

        return Response(res, status=status.HTTP_200_OK)


class CloseDayView(APIView):
    """
    close day view
    """

    def get(self, request):
        device = Device.objects.first()
        fiscal_day = FiscalDay.objects.filter(
            is_open=True
        ).first()  # TODO: circuit breaker
        fiscal_counters = fiscal_day.counters.all()
        tax_map = {t.tax_id: t.name for t in Taxes.objects.all()}

        logger.info(fiscal_counters)

        service = ClosingDayService(
            device=device,
            fiscal_day=fiscal_day,
            fiscal_counters=fiscal_counters,
            tax_map=tax_map,
            receipt_handler=receipt_handler,
        )

        closing_string, payload = service.close_day()

        logger.info(f"Closing Fiscal Day string: {closing_string}")
        logger.info(f"Closing payload: {payload}")

        client.close_day(payload)
        status_payload = client.get_status()

        return Response(status_payload, status=status.HTTP_200_OK)
