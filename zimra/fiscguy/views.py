from django.shortcuts import render
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from fiscguy.models import Configuration, Receipt, Taxes, Device
from fiscguy.serializers import (
    ConfigurationSerializer,
    ReceiptLineSerializer, 
    ReceiptSerializer,
    TaxSerializer

)
from fiscguy.zimra_base import ZIMRAClient
from fiscguy.zimra_receipt_handler import ZIMRAReceiptHandler

from loguru import logger 
from easy_pagination import NoPagination, StandardPagination

client = ZIMRAClient(Device.objects.first())
receipt_handler = ZIMRAReceiptHandler()

class ReceiptView(generics.GenericAPIView):
    serializer_class = ReceiptSerializer
    # pagination_class = StandardPagination
    # permission_classes = [
    #     IsAuthenticated,
    # ]
    queryset = Receipt.objects.all()

    def get(self, request):
        data = self.queryset.order_by("created_at").select_related(
            "buyer"
        )
        return Response(data)

    def post(self, request):
        serializer = ReceiptSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            receipt_handler.generate_receipt_data()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


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
        return Response(
            self.serializer_class(config).data,
            status=status.HTTP_200_OK
        )

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
    def get(self, request):
        res = client.get_status()
        return Response(res, status=status.HTTP_200_OK)


class OpenDayView(APIView):
    def get(self, request):
        res = client.open_day()
        return Response(res, status=status.HTTP_200_OK)
 
    
class CloseDayView(APIView):
    pass
    


