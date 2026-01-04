from rest_framework import serializers

from fiscguy.models import Buyer, Configuration, Receipt, ReceiptLine, Taxes


class ConfigurationSerializer(serializers.ModelSerializer):
    """
    configurations for the taxpayer
    """

    class Meta:
        model = Configuration
        fields = [
            "id",
            "tax_payer_name",
            "tin_number",
            "vat_number",
            "address",
            "phone_number",
            "email",
        ]


class TaxSerializer(serializers.ModelSerializer):
    """
    Zimra official taxes
    """

    class Meta:
        model = Taxes
        fields = "__all__"


class ReceiptLineSerializer(serializers.ModelSerializer):
    """
    Receipt lines
    """

    tax_type = serializers.StringRelatedField()

    class Meta:
        model = ReceiptLine
        fields = [
            "id",
            "product",
            "quantity",
            "unit_price",
            "line_total",
            "tax_amount",
            "tax_type",
        ]


class BuyerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Buyer
        fields = [
            "id",
            "name",
            "address",
            "tin_number",
            "vat_numberr",
        ]


class ReceiptSerializer(serializers.ModelSerializer):
    """
    Receipt Serialiazerr
    """

    lines = ReceiptLineSerializer(many=True, read_only=True)
    buyer = BuyerSerializer(read_only=True)

    class Meta:
        model = Receipt
        fields = "__all__"


class ReceiptCreateSerializer(serializers.ModelSerializer):
    lines = ReceiptLineSerializer(many=True)

    class Meta:
        model = Receipt
        fields = [
            "receipt_type",
            "total_amount",
            "currency",
            "buyer",
            "lines",
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")

        receipt = Receipt.objects.create(**validated_data)

        for line_data in lines_data:
            ReceiptLine.objects.create(receipt=receipt, **line_data)
        return receipt
