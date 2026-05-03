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
            "hs_code": "22030000",
            "tax_id": 517,
            "quantity": "1",
            "unit_price": "115.00",
            "line_total": "115.00",
            "tax_amount": "15.00",
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
            "hs_code": "22030000",      # Optional if inherited from original receipt line
            "tax_id": 517,
            "quantity": "1",
            "unit_price": "-115.00",    # Must be < 0 for Sale lines
            "line_total": "-115.00",
            "tax_amount": "-15.00",
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
- If `hs_code` is omitted, FiscGuy can inherit it from the referenced original receipt line

---

## Debit Note (`debitnote`)

An upward adjustment against a previously issued fiscal invoice (e.g. additional charges).

```python
receipt = submit_receipt({
    "receipt_type": "debitnote",
    "currency": "USD",
    "total_amount": "23.00",
    "payment_terms": "Card",
    "debit_note_reason": "Additional delivery charge",
    "debit_note_reference": "R-00000142",
    "lines": [
        {
            "product": "Delivery fee",
            "hs_code": "99001000",      # Optional when inherited or resolved by fallback
            "tax_id": 517,
            "quantity": "1",
            "unit_price": "23.00",
            "line_total": "23.00",
            "tax_amount": "3.00",
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

**Rules (ZIMRA spec):**
- `receiptTotal` must be `>= 0`
- `receiptNotes` (reason) is mandatory
- `creditDebitNote` reference to original invoice is mandatory
- `paymentAmount` must be `>= 0`
- If `hs_code` is omitted, FiscGuy first tries to inherit it from the referenced original
  receipt line; if no matching product line is found, it falls back to the ZIMRA service HS
  codes for service/intangible adjustments

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
| 517 | Standard Rated 15.5% | 15.5% |

When building a receipt line, pass the FDMS `tax_id` from the synced `Taxes` table. The
recommended flow is:

1. Call `GET /fiscguy/taxes/`
2. Choose the correct `tax_id` for the item being sold
3. Send that `tax_id` on each receipt line

### HS Code Guidance

- `hs_code` should be included in receipt-line payloads for normal invoice flows
- Firms should map their product and service catalogues to the correct FDMS-compatible HS codes
- Credit notes can inherit `hs_code` from the referenced original receipt line
- Debit notes can inherit `hs_code` from the referenced original receipt line or, for
  service/intangible adjustments, fall back to the ZIMRA service codes:
  `99001000`, `99002000`, `99003000`

---

## Buyer Data (Optional)

Attach buyer registration data to any receipt type:

```python
# Create a buyer first
from fiscguy.models import Buyer
buyer = Buyer.objects.create(
    name="Cas Bz",
    tin_number="1234567890",
    email="accounts@casbz.co.zw",
)

# Pass buyer ID in receipt payload
receipt = submit_receipt({
    ...
    "buyer": buyer.id,
})
```

ZIMRA requires both `buyerRegisterName` and `buyerTIN` if buyer data is included (RCPT043).
