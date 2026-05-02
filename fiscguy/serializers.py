from django.db import transaction
from rest_framework import serializers

from fiscguy.models import Buyer, Configuration, Device, Receipt, ReceiptLine, Taxes


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = [
            "id",
            "org_name",
            "activation_key",
            "device_id",
            "device_model_name",
            "device_serial_number",
            "device_model_version",
            "production",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ConfigurationSerializer(serializers.ModelSerializer):
    """
    configurations for the taxpayer
    """

    class Meta:
        model = Configuration
        fields = [
            "id",
            "device",
            "tax_payer_name",
            "tin_number",
            "vat_number",
            "address",
            "phone_number",
            "email",
            "device_operating_mode",
            "tax_payer_day_max_hrs",
            "tax_payer_day_end_notification_hrs",
            "certificate_valid_till",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TaxSerializer(serializers.ModelSerializer):
    """
    Zimra official taxes
    """

    class Meta:
        model = Taxes
        fields = "__all__"
        read_only_fields = ["id", "created_at"]


class ReceiptLineSerializer(serializers.ModelSerializer):
    """
    Receipt lines
    """

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
        read_only_fields = ["id"]


class ReceiptLineCreateSerializer(serializers.ModelSerializer):
    """
    Writable serializer for receipt lines used when creating receipts.
    """

    tax_name = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = ReceiptLine
        fields = [
            "product",
            "quantity",
            "unit_price",
            "line_total",
            "tax_amount",
            "tax_name",
        ]


class BuyerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Buyer
        fields = [
            "id",
            "name",
            "address",
            "tin_number",
            "trade_name",
            "email",
            "phonenumber",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ReceiptSerializer(serializers.ModelSerializer):
    """
    Receipt Serializer
    """

    lines = ReceiptLineSerializer(many=True, read_only=True)
    buyer = BuyerSerializer(read_only=True)

    class Meta:
        model = Receipt
        fields = [
            "id",
            "device",
            "receipt_number",
            "receipt_type",
            "total_amount",
            "qr_code",
            "code",
            "currency",
            "global_number",
            "hash_value",
            "signature",
            "zimra_inv_id",
            "buyer",
            "payment_terms",
            "submitted",
            "is_credit_note",
            "credit_note_reason",
            "credit_note_reference",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ReceiptCreateSerializer(serializers.ModelSerializer):
    lines = ReceiptLineCreateSerializer(many=True)
    buyer = BuyerSerializer(required=False, allow_null=True)

    credit_note_reference = serializers.CharField(required=False, allow_blank=True)
    credit_note_reason = serializers.CharField(required=False, allow_blank=True)
    debit_note_reference = serializers.CharField(required=False, allow_blank=True, write_only=True)
    debit_note_reason = serializers.CharField(required=False, allow_blank=True, write_only=True)
    payment_terms = serializers.ChoiceField(choices=Receipt.PaymentMethod.choices)

    class Meta:
        model = Receipt
        fields = [
            "device",
            "receipt_type",
            "total_amount",
            "currency",
            "buyer",
            "lines",
            "payment_terms",
            "credit_note_reference",
            "credit_note_reason",
            "debit_note_reference",
            "debit_note_reason",
        ]

    def validate(self, attrs):
        receipt_type = attrs.get("receipt_type", "").lower()
        total_amount = attrs.get("total_amount", 0)
        reference, reason = self._resolve_note_fields(attrs)

        if receipt_type in {"creditnote", "debitnote"}:
            if not reference:
                raise serializers.ValidationError(
                    {"credit_note_reference": "This field is required for credit and debit notes"}
                )

            if not reason:
                raise serializers.ValidationError(
                    {"credit_note_reason": "This field is required for credit and debit notes"}
                )

            if not Receipt.objects.filter(receipt_number=reference).exists():
                raise serializers.ValidationError(
                    {"credit_note_reference": "Referenced receipt does not exist"}
                )

        if receipt_type == "creditnote" and total_amount > 0:
            raise serializers.ValidationError(
                {"total_amount": "Credit note total must be negative"}
            )

        if receipt_type == "debitnote" and total_amount < 0:
            raise serializers.ValidationError({"total_amount": "Debit note total must be positive"})

        attrs["credit_note_reference"] = reference
        attrs["credit_note_reason"] = reason
        attrs.pop("debit_note_reference", None)
        attrs.pop("debit_note_reason", None)

        return attrs

    def create(self, validated_data):

        buyer_data = validated_data.pop("buyer", None)
        lines_data = validated_data.pop("lines")
        receipt_type = validated_data.get("receipt_type", "").lower()

        with transaction.atomic():

            buyer = None

            if buyer_data:
                # validate tin number
                if len(buyer_data["tin_number"]) != 10:
                    raise serializers.ValidationError(
                        {"buyer": "Tin number is incorrect, must be ten digit."}
                    )

                buyer, _ = Buyer.objects.get_or_create(
                    tin_number=buyer_data["tin_number"].strip(),
                    defaults={
                        "name": buyer_data["name"].strip(),  # business registered name
                        "email": buyer_data["email"].strip(),
                        "trade_name": buyer_data[
                            "trade_name"
                        ].strip(),  # trade name e.g branch name
                        "phonenumber": buyer_data["phonenumber"].strip(),
                        "address": buyer_data["address"].strip(),
                    },
                )

            receipt = Receipt.objects.create(**validated_data)

            if buyer:
                receipt.buyer = buyer
                receipt.save()

            for idx, line_data in enumerate(lines_data):

                tax_name = line_data.pop("tax_name", None)

                if tax_name:
                    tax = (
                        Taxes.objects.filter(name__iexact=tax_name.strip()).first()
                        or Taxes.objects.filter(name__icontains=tax_name.strip()).first()
                    )

                    if not tax:
                        raise serializers.ValidationError(
                            {"lines": {idx: f"Tax with name '{tax_name}' not found"}}
                        )

                    line_data["tax_type"] = tax

                if receipt_type == "creditnote":
                    if line_data.get("unit_price", 0) > 0:
                        line_data["unit_price"] *= -1

                    if line_data.get("line_total", 0) > 0:
                        line_data["line_total"] *= -1

                    receipt.is_credit_note = True
                    receipt.save()

                ReceiptLine.objects.create(receipt=receipt, **line_data)

            return receipt

    @staticmethod
    def _resolve_note_fields(attrs):
        reference = (
            attrs.get("credit_note_reference") or attrs.get("debit_note_reference") or ""
        ).strip()
        reason = (attrs.get("credit_note_reason") or attrs.get("debit_note_reason") or "").strip()
        return reference, reason
