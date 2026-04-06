# Receipt Types

FiscGuy supports three receipt types as defined by the ZIMRA Fiscal Device Gateway API.

---

## Fiscal Invoice (`fiscalinvoice`)

A standard sale receipt. The most common receipt type.

```python
from fiscguy import submit_receipt

receipt = submit_receipt({
    "receipt_type": "fiscalinvoice",
    "currency": "USD",
    "total_amount": "115.00",
    "payment_terms": "Cash",
    "lines": [
        {
            "product": "Product Name",
            "quantity": "1",
            "unit_price": "115.00",
            "line_total": "115.00",
            "tax_amount": "15.00",
            "tax_name": "standard rated 15%",
        }
    ],
})
```

**Counter impact:**

| Counter | Value |
|---------|-------|
| `SaleByTax` | `+salesAmountWithTax` per tax group |
| `SaleTaxByTax` | `+taxAmount` per tax group (non-exempt, non-zero only) |
| `BalanceByMoneyType` | `+paymentAmount` |

**Rules:**
- `receiptTotal` must be `>= 0`
- `receiptLinePrice` must be `> 0` for Sale lines
- `paymentAmount` must be `>= 0`

---

## Credit Note (`creditnote`)

A return or reversal against a previously issued fiscal invoice.

```python
receipt = submit_receipt({
    "receipt_type": "creditnote",
    "currency": "USD",
    "total_amount": "-115.00",          # Must be <= 0
    "payment_terms": "Cash",
    "credit_note_reason": "Customer returned goods — defective",
    "credit_note_reference": "R-00000142",  # Original receipt number
    "lines": [
        {
            "product": "Product Name",
            "quantity": "1",
            "unit_price": "-115.00",    # Must be < 0 for Sale lines
            "line_total": "-115.00",
            "tax_amount": "-15.00",
            "tax_name": "standard rated 15%",
        }
    ],
})
```

**Counter impact:** Credit note amounts are **negative**, so each counter decreases:

| Counter | Value |
|---------|-------|
| `CreditNoteByTax` | `+salesAmountWithTax` (negative) per tax group |
| `CreditNoteTaxByTax` | `+taxAmount` (negative) per tax group (non-exempt, non-zero only) |
| `BalanceByMoneyType` | `+paymentAmount` (negative) |

**Rules (ZIMRA spec):**
- `receiptTotal` must be `<= 0`
- `receiptNotes` (credit_note_reason) is **mandatory**
- `creditDebitNote` reference to original invoice is **mandatory**
- Original receipt must exist in FDMS (RCPT032)
- Original receipt must have been issued within the last 12 months (RCPT033)
- Total credit amount must not exceed the original receipt amount net of prior credits (RCPT035)
- Tax types must be a subset of those on the original invoice — you cannot introduce new tax types (RCPT036)
- Currency must match the original invoice (RCPT043)
- `receiptLinePrice` must be `< 0` for Sale lines
- `paymentAmount` must be `<= 0`

---

## Debit Note (`debitnote`)

An upward adjustment against a previously issued fiscal invoice (e.g. additional charges).

```python
receipt = submit_receipt({
    "receipt_type": "debitnote",
    "currency": "USD",
    "total_amount": "23.00",
    "payment_terms": "Card",
    "credit_note_reason": "Additional delivery charge",
    "credit_note_reference": "R-00000142",
    "lines": [
        {
            "product": "Delivery fee",
            "quantity": "1",
            "unit_price": "23.00",
            "line_total": "23.00",
            "tax_amount": "3.00",
            "tax_name": "standard rated 15%",
        }
    ],
})
```

**Counter impact:**

| Counter | Value |
|---------|-------|
| `DebitNoteByTax` | `+salesAmountWithTax` per tax group |
| `DebitNoteTaxByTax` | `+taxAmount` per tax group |
| `BalanceByMoneyType` | `+paymentAmount` |

---

## Payment Methods

| Value | Description |
|-------|-------------|
| `Cash` | Physical cash |
| `Card` | Credit or debit card |
| `MobileWallet` | Mobile money (EcoCash, etc.) |
| `BankTransfer` | Direct bank transfer |
| `Coupon` | Voucher or coupon |
| `Credit` | Credit account |
| `Other` | Any other method |

---

## Tax Types

Taxes are fetched from FDMS on every `open_day()` and stored in the `Taxes` model.

```python
from fiscguy.models import Taxes

for tax in Taxes.objects.all():
    print(f"{tax.tax_id}: {tax.name} @ {tax.percent}%")
```

Typical ZIMRA tax types:

| Tax ID | Name | Percent |
|--------|------|---------|
| 1 | Exempt | 0% |
| 2 | Zero Rated 0% | 0% |
| 3+ | Standard Rated | 15.5% |

When building a receipt line, pass the `tax_name` exactly as it appears in `Taxes.name` so the correct `tax_id` and `tax_percent` are resolved.

---

## Buyer Data (Optional)

Attach buyer registration data to any receipt type:

```python
# Create a buyer first
from fiscguy.models import Buyer
buyer = Buyer.objects.create(
    name="AC",
    tin_number="1234567890",
    email="accounts@acme.co.zw",
)

# Pass buyer ID in receipt payload
receipt = submit_receipt({
    ...
    "buyer": buyer.id,
})
```

ZIMRA requires both `buyerRegisterName` and `buyerTIN` if buyer data is included (RCPT043).
