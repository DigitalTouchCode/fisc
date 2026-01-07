from django.db import models


class Device(models.Model):
    org_name = models.CharField(max_length=255)
    activation_key = models.CharField(max_length=255)
    device_id = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    device_model_name = models.CharField(max_length=255, null=True)
    device_serial_number = models.CharField(max_length=255, null=True)
    device_model_version = models.CharField(max_length=255, null=True)
    production = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.org_name} - {self.device_id}"


class Configuration(models.Model):
    """
    Zimra taxpayer configuration
    """

    tax_payer_name = models.CharField(max_length=255)
    tax_inclusive = models.BooleanField(default=True)
    tin_number = models.CharField(max_length=20)
    vat_number = models.CharField(max_length=20)
    address = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField()
    url = models.URLField(
        null=True, blank=True
    )  # for zimra either testing or production

    def __str__(self):
        return self.tax_payer_name


class Certs(models.Model):
    """
    Zimra certificates for authentication,
    divided between production and testing certs
    """

    csr = models.TextField()
    certificate = models.TextField()
    certificate_key = models.TextField()
    production = models.BooleanField(default=False)

    def __str__(self):
        env = "Production" if self.production else "Testing"
        return f"{env} Certificate"


class Taxes(models.Model):
    """
    Zimra taxes automatically update on every day opening
    """

    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    tax_id = models.IntegerField()
    percent = models.FloatField()

    def __str__(self):
        return f"{self.name}: {self.percent}"


class FiscalDay(models.Model):
    """
    Fiscal day model (increment with +1 every opening, keeps the receipt counter of the day)
    """

    day_no = models.IntegerField()
    receipt_counter = models.IntegerField()
    is_open = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Day No: {self.day_no} | Open: {self.is_open}"


class FiscalCounter(models.Model):
    """
    Fiscal counter model
    """

    SALE_BY_TAX = "SaleByTax"
    SALE_BY_VAT = "SaleByVAT"
    SALE_TAX_BY_TAX = "SaleTaxByTax"
    Balancebymoneytype = "Balancebymoneytype"
    OTHER = "Other"

    COUNTER_TYPE_CHOICES = [
        (SALE_BY_TAX, "SaleByTax"),
        (SALE_BY_VAT, "SaleByVAT"),
        (SALE_TAX_BY_TAX, "SaleTaxByTax"),
        (Balancebymoneytype, "Balancebymoneytype"),
    ]

    CASH = "Cash"
    CARD = "Card"
    BANK_TRANSFER = "BankTransfer"
    MOBILE_MONEY = "MobileMoney"

    MONEY_TYPE_CHOICES = [
        (CASH, "Cash"),
        (CARD, "Card"),
        (BANK_TRANSFER, "Bank Transfer"),
        (MOBILE_MONEY, "Mobile Money"),
    ]

    fiscal_day = models.ForeignKey(
        FiscalDay,
        on_delete=models.CASCADE,
        related_name="counters",
        null=True,
        blank=True,
    )
    fiscal_counter_type = models.CharField(
        max_length=30, choices=COUNTER_TYPE_CHOICES, default=SALE_BY_TAX
    )
    fiscal_counter_currency = models.CharField(
        max_length=10, choices=[("USD", "usd"), ("ZWG", "zwg")], default="USD"
    )
    fiscal_counter_tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00, null=True, blank=True
    )
    fiscal_counter_tax_id = models.IntegerField(default=3)
    fiscal_counter_money_type = models.CharField(
        max_length=20, choices=MONEY_TYPE_CHOICES, default=CASH, null=True
    )
    fiscal_counter_value = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f": ({self.fiscal_counter_type} - {self.fiscal_counter_currency} - {self.fiscal_counter_value})"


class Receipt(models.Model):
    """
    Receiipt model
    """

    class ReceiptType(models.TextChoices):
        FISCAL_INVOICE = "fiscalinvoice", "Fiscal Invoice"
        CREDIT_NOTE = "creditnote", "Creditnote"
        DEBIT_NOTE = "debitnote", "Debitnote"

    receipt_number = models.CharField(
        unique=True, max_length=255, null=True, blank=True
    )
    receipt_type = models.CharField(
        choices=ReceiptType, default=ReceiptType.FISCAL_INVOICE, max_length=255
    )
    total_amount = models.FloatField()
    qr_code = models.ImageField(upload_to="Zimra_qr_codes", null=True, blank=True)
    code = models.CharField(max_length=20, null=True, blank=True)
    currency = models.CharField(
        max_length=255, choices=[("USD", "usd"), ("ZWG", "zwg")], default="USD"
    )

    global_number = models.IntegerField(null=True, blank=True)
    hash_value = models.CharField(max_length=255, null=True, blank=True)
    signature = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)

    zimra_inv_id = models.CharField(max_length=255, null=True)

    buyer = models.ForeignKey(
        "Buyer",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="receipts",
    )
    payment_terms = models.CharField(max_length=200)
    submitted = models.BooleanField(default=False, null=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new and not self.receipt_number:
            self.receipt_number = f"R-{self.id:06d}"
            super().save(update_fields=["receipt_number"])

    def __str__(self):
        return f"Receipt No: {self.receipt_number} | Type: {self.receipt_type} | Total: {self.total_amount}"


class ReceiptLine(models.Model):
    """
    Receipt lines model, (product can vary with different taxes)
    """

    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="lines")
    product = models.CharField(max_length=255)
    quantity = models.IntegerField()
    unit_price = models.FloatField()
    line_total = models.FloatField()
    tax_amount = models.FloatField()
    tax_type = models.ForeignKey(Taxes, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return f"{self.product} - {self.line_total}"


class Buyer(models.Model):
    """
    Buyer model (not mansatory on every transaction)
    """

    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    tin_number = models.CharField(max_length=255)
    vat_numberr = models.CharField(max_length=255)

    def __str__(self):
        return self.name
