from django.shortcuts import render
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from fiscguy.models import Configuration, Receipt
from fiscguy.serializers import (ConfigurationSerializer,
                                 ReceiptLineSerializer, ReceiptSerializer)

# from easy_pagination import


class ReceiptView(generics.GenericAPIView):
    serializer_class = ReceiptSerializer
    # permission_classes = [
    #     IsAuthenticated,
    # ]

    def get(self, request):
        data = Receipt.objects.order_by("created_at").select_related(
            "receipt_lines", "buyer"
        )
        return Response(data)

    def post(self, request):
        serializer = ReceiptSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class ReceiptDetailView(generics.RetrieveAPIView):
    queryset = Receipt.objects.all().select_related("receipt_lines", "buyer")
    serializer_class = ReceiptSerializer
    lookup_field = "id"


class ConfigurationView(ModelViewSet):
    """
    CRUD view for Zimra Configuration
    """

    queryset = Configuration.objects
    serializer_class = ConfigurationSerializer


class DeviceRegistration(APIView):
    pass
