# FiscGuy User & Integration Guide

**FiscGuy** Python library for integrating with ZIMRA (Zimbabwe Revenue Authority) fiscal devices. It simplifies fiscal operations through a clean REST API and robust business logic.

**Table of Contents:**
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
- [Usage Examples](#usage-examples)
- [Concepts](#concepts)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

---

## Features

✅ **Secure Device Integration** - Certificate-based mutual TLS with ZIMRA FDMS

✅ **Receipt Management** - Create, sign, and submit receipts with multiple tax types

✅ **Fiscal Day Operations** - Automatic fiscal day management with counter tracking

✅ **Device Configuration** - Sync taxpayer info and tax rates from ZIMRA

✅ **Credit/Debit Notes** - Issue refunds and adjustments per ZIMRA spec

✅ **Multi-Currency Support** - Handle USD and ZWG transactions

✅ **QR Code Generation** - Auto-generate receipt verification QR codes

✅ **Fully Tested** - 90%+ code coverage, 22+ test cases

✅ **Production Ready** - Used in live ZIMRA deployments

---

## Installation

### Via PyPI

```bash
pip install fiscguy
```

### From Source

```bash
git clone https://github.com/digitaltouchcode/fisc.git
cd fisc
pip install -e .
```

### Requirements

- Python 3.11+ (tested on 3.11, 3.12, 3.13)
- Django 4.2+
- Django REST Framework 3.14+

---

## Quick Start

### Step 1: Add to Django Settings

```python
# settings.py
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'rest_framework',
    'fiscguy',  # Add this
]
```

### Step 2: Run Migrations

```bash
python manage.py makemigrations fiscguy
python manage.py migrate fiscguy
```

### Step 3: Include URLs

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    path('api/', include('fiscguy.urls')),
]
```

### Step 4: Register Your Device

```bash
python manage.py init_device
```

This interactive command will:
- Collect device information (org name, device ID, model)
- Generate and register certificates with ZIMRA
- Sync device configuration and tax rates
- Confirm successful registration

**⚠️ Environment Switching:**
If switching from test to production (or vice versa), the command warns you and requires confirmation to delete all test/old production data.

### Step 5: Make Your First Request

```bash
curl -X GET http://localhost:8000/api/configuration/ \
  -H "Content-Type: application/json"
```

You should receive your device configuration.

---

## API Endpoints

### Receipt Management

#### Create & Submit Receipt (Auto-opens day if needed)
```
POST /api/receipts/
Content-Type: application/json

{
  "receipt_type": "fiscalinvoice",
  "total_amount": "100.00",
  "currency": "USD",
  "payment_terms": "Cash",
  "lines": [
    {
      "product": "Product Name",
      "quantity": "1",
      "unit_price": "100.00",
      "line_total": "100.00",
      "tax_name": "standard rated 15.5%"
    }
  ]
}

Returns: 201 Created
{
  "id": 1,
  "device": 1,
  "receipt_number": "R-00000001",
  "receipt_type": "fiscalinvoice",
  "total_amount": "100.00",
  "qr_code": "https://...",
  "code": "ABC1234567890",
  "hash_value": "base64...",
  "signature": "base64...",
  "zimra_inv_id": "ZIM-123456",
  "submitted": true,
  "created_at": "2026-04-01T10:30:00Z"
}
```

#### List Receipts (Paginated)
```
GET /api/receipts/?page_size=20

Returns: 200 OK
{
  "next": "https://api/receipts/?cursor=...",
  "previous": null,
  "results": [...]
}
```

#### Get Receipt Details
```
GET /api/receipts/{id}/

Returns: 200 OK
{
  "id": 1,
  "receipt_number": "R-00000001",
  "lines": [
    {
      "id": 1,
      "product": "Product",
      "quantity": "1",
      "unit_price": "100.00",
      "line_total": "100.00",
      "tax_amount": "15.50",
      "tax_type": "standard rated 15.5%"
    }
  ],
  "buyer": null,
  ...
}
```

### Fiscal Day Management

#### Open Fiscal Day
```
POST /api/open-day/

Returns: 200 OK
{
  "fiscal_day_number": 1,
  "is_open": true,
  "message": "Fiscal day opened"
}
```

**Note:** Automatically called when submitting the first receipt of the day.

#### Close Fiscal Day
```
POST /api/close-day/

Returns: 200 OK
{
  "fiscal_day_number": 1,
  "is_open": false,
  "receipt_count": 15,
  "message": "Fiscal day closed"
}
```

**What happens:**
- Sums all receipt counters (by type, currency, tax)
- Sends closing hash to ZIMRA
- Resets fiscal day for next day's receipts

### Device Management

#### Get Device Status
```
GET /api/get-status/

Returns: 200 OK
{
  "device_id": "ABC123",
  "org_name": "My Business",
  "is_online": true,
  "open_fiscal_day": 1,
  "last_receipt_no": "R-00000042",
  "last_receipt_global_no": 42
}
```

#### Get Device Configuration
```
GET /api/configuration/

Returns: 200 OK
{
  "id": 1,
  "device": 1,
  "tax_payer_name": "My Business Ltd",
  "tin_number": "1234567890",
  "vat_number": "VAT123",
  "address": "123 Main St",
  "phone_number": "+263123456789",
  "email": "info@mybusiness.com"
}
```

#### Sync Configuration & Taxes
```
POST /api/sync-config/

Returns: 200 OK
{
  "config_synced": true,
  "taxes_synced": true,
  "tax_count": 5,
  "message": "Configuration synchronized"
}
```

### Taxes

#### List Available Taxes
```
GET /api/taxes/

Returns: 200 OK
[
  {
    "id": 1,
    "code": "STD",
    "name": "standard rated 15.5%",
    "tax_id": 1,
    "percent": "15.50"
  },
  {
    "id": 2,
    "code": "ZRO",
    "name": "zero rated 0%",
    "tax_id": 4,
    "percent": "0.00"
  },
  {
    "id": 3,
    "code": "EXM",
    "name": "exempt 0%",
    "tax_id": 5,
    "percent": "0.00"
  }
]
```

### Buyers (Optional)

#### List Buyers
```
GET /api/buyer/

Returns: 200 OK
[
  {
    "id": 1,
    "name": "John's Retail",
    "tin_number": "1234567890",
    "trade_name": "John's Store",
    "email": "john@retail.com",
    "address": "456 Commerce Ave",
    "phonenumber": "+263987654321"
  }
]
```

#### Create Buyer
```
POST /api/buyer/
Content-Type: application/json

{
  "name": "Jane's Shop",
  "tin_number": "0987654321",
  "trade_name": "Jane's Retail",
  "email": "jane@shop.com",
  "address": "789 Business St",
  "phonenumber": "+263111111111"
}

Returns: 201 Created
```

#### Update Buyer
```
PATCH /api/buyer/{id}/

Returns: 200 OK
```

#### Delete Buyer
```
DELETE /api/buyer/{id}/

Returns: 204 No Content
```

---

## Usage Examples

### Example 1: Simple Cash Receipt

```bash
curl -X POST http://localhost:8000/api/receipts/ \
  -H "Content-Type: application/json" \
  -d '{
    "receipt_type": "fiscalinvoice",
    "total_amount": "150.00",
    "currency": "USD",
    "payment_terms": "Cash",
    "lines": [
      {
        "product": "Bread",
        "quantity": "2",
        "unit_price": "50.00",
        "line_total": "100.00",
        "tax_name": "standard rated 15.5%"
      },
      {
        "product": "Milk",
        "quantity": "1",
        "unit_price": "43.48",
        "line_total": "50.00",
        "tax_name": "exempt 0%"
      }
    ]
  }'
```

**Response:**
```json
{
  "id": 5,
  "receipt_number": "R-00000005",
  "receipt_type": "fiscalinvoice",
  "total_amount": "150.00",
  "submitted": true,
  "zimra_inv_id": "ZIM-789012"
}
```

### Example 2: Receipt with Buyer

```bash
curl -X POST http://localhost:8000/api/receipts/ \
  -H "Content-Type: application/json" \
  -d '{
    "receipt_type": "fiscalinvoice",
    "total_amount": "500.00",
    "currency": "USD",
    "payment_terms": "BankTransfer",
    "buyer": {
      "name": "Tech Solutions Ltd",
      "tin_number": "1234567890",
      "trade_name": "Tech Shop",
      "email": "tech@example.com",
      "address": "123 Tech Park",
      "phonenumber": "+263123456789"
    },
    "lines": [
      {
        "product": "Laptop",
        "quantity": "1",
        "unit_price": "400.00",
        "line_total": "400.00",
        "tax_name": "standard rated 15.5%"
      },
      {
        "product": "Warranty",
        "quantity": "1",
        "unit_price": "100.00",
        "line_total": "100.00",
        "tax_name": "standard rated 15.5%"
      }
    ]
  }'
```

### Example 3: Credit Note (Refund)

```bash
# First, get the receipt number to refund
curl -X GET http://localhost:8000/api/receipts/

# Then issue a credit note
curl -X POST http://localhost:8000/api/receipts/ \
  -H "Content-Type: application/json" \
  -d '{
    "receipt_type": "creditnote",
    "credit_note_reference": "R-00000005",
    "credit_note_reason": "Customer returned item",
    "total_amount": "-100.00",
    "currency": "USD",
    "payment_terms": "Cash",
    "lines": [
      {
        "product": "Bread (Returned)",
        "quantity": "2",
        "unit_price": "-50.00",
        "line_total": "-100.00",
        "tax_name": "standard rated 15.5%"
      }
    ]
  }'
```

**Key differences:**
- `receipt_type`: "creditnote"
- `total_amount`: negative
- `line_total` and `unit_price`: negative
- `credit_note_reference`: original receipt number (must exist)

### Example 4: Integration with Django Code

```python
from fiscguy.models import Receipt, ReceiptLine, Buyer
from fiscguy.services.receipt_service import ReceiptService
from fiscguy.models import Device

# Get the device
device = Device.objects.first()

# Create receipt data
receipt_data = {
    "device": device.id,
    "receipt_type": "fiscalinvoice",
    "total_amount": "100.00",
    "currency": "USD",
    "payment_terms": "Cash",
    "lines": [
        {
            "product": "Service",
            "quantity": "1",
            "unit_price": "100.00",
            "line_total": "100.00",
            "tax_name": "standard rated 15.5%"
        }
    ]
}

# Create and submit receipt
service = ReceiptService(device)
receipt, submission_result = service.create_and_submit_receipt(receipt_data)

print(f"Receipt created: {receipt.receipt_number}")
print(f"Submitted to ZIMRA: {receipt.submitted}")
print(f"ZIMRA ID: {receipt.zimra_inv_id}")
```

---

## Concepts

### Fiscal Device

A physical or logical device registered with ZIMRA. Each device has:
- **Unique device ID** - Assigned during registration
- **Certificates** - For ZIMRA authentication (test and/or production)
- **Configuration** - Taxpayer info (TIN, name, address, VAT number)
- **Fiscal Days** - Daily accounting periods
- **Receipts** - All issued receipts

### Fiscal Day

An accounting period (usually daily) during which:
1. Receipts are issued and signed with cryptographic material
2. Receipt counters accumulate (by type, currency, tax)
3. Day is closed with a closing hash sent to ZIMRA
4. Cannot reopen a closed fiscal day

**Important:** First receipt automatically opens the day if needed.

### Receipt Types

| Type | Description | Receiver | Amount Sign |
|------|-------------|----------|-------------|
| **Fiscal Invoice** | Normal sale | Customer | Positive (+) |
| **Credit Note** | Refund/discount | Customer | Negative (-) |
| **Debit Note** | Surcharge/adjustment | Customer | Positive (+) |

### Receipt Counters

FiscGuy tracks counters by:
- **Type**: SaleByTax, SaleTaxByTax, CreditNoteByTax, etc.
- **Currency**: USD or ZWG
- **Tax Rate**: Standard, Zero-Rated, Exempt, Withholding

Counters are summed at day-close and sent to ZIMRA.

### Payment Methods

- Cash
- Card
- Bank Transfer
- Mobile Wallet
- Coupon
- Credit
- Other

### Tax Types (Synced from ZIMRA)

- **Standard Rated** (typically 15.5%)
- **Zero Rated** (0%, e.g., exports)
- **Exempt** (0%, e.g., education)
- **Withholding** (applied by buyer)

---

## Troubleshooting

### Issue: "No open fiscal day and FDMS is unreachable"

**Cause:** Network error or ZIMRA is offline during first receipt submission.

**Solution:**
1. Check internet connectivity
2. Verify ZIMRA API availability
3. Ensure device certificates are valid
4. Manually open day: `POST /api/open-day/`

### Issue: "ZIMRA configuration missing"

**Cause:** Device configuration not synced.

**Solution:**
```bash
python manage.py init_device
# Or:
curl -X POST http://localhost:8000/api/sync-config/
```

### Issue: "TIN number is incorrect, must be ten digit"

**Cause:** Buyer TIN is not exactly 10 digits.

**Solution:**
- Format TIN as 10 digits (e.g., `0123456789`)
- Pad with leading zeros if needed

### Issue: "Tax with name 'X' not found"

**Cause:** Requested tax doesn't exist in database.

**Solution:**
1. Check available taxes: `GET /api/taxes/`
2. Use exact tax name from list
3. Sync taxes: `POST /api/sync-config/`

### Issue: "Referenced receipt does not exist" (Credit Note)

**Cause:** Trying to create credit note for receipt that doesn't exist locally.

**Solution:**
- Verify original receipt number is correct
- Original receipt must be submitted to ZIMRA before creating credit note

### Issue: Timeout or "FDMS error" in logs

**Cause:** ZIMRA API timeout (>30 seconds).

**Solution:**
- Check network latency to ZIMRA servers
- Retry the request
- Monitor ZIMRA status page

### Issue: "Device is not registered"

**Cause:** Device table is empty.

**Solution:**
```bash
python manage.py init_device
```

### Issue: Receipts not marked as `submitted=True`

**Cause:** ZIMRA API call failed or device is offline.

**Solution:**
- Check ZIMRA connectivity
- Review server logs for error details
- Re-submit receipt (transaction ensures atomicity)

---

## FAQ

### Q: Do I need to manually open fiscal days?

**A:** No, the first receipt of the day automatically opens it. You only manually open if needed.

### Q: Can I use multiple devices?

**A:** Yes, FiscGuy supports multiple devices. Each device has its own config and receipts. Note: The API uses `Device.objects.first()`, so you may want to extend views for device selection.

### Q: What happens if ZIMRA is offline?

**A:** Receipts fail submission with `ReceiptSubmissionError`. The receipt is rolled back (not saved). Retry when ZIMRA is back online.

### Q: Can I issue credit notes for receipts from another system?

**A:** No, the original receipt must exist in FiscGuy's database and be submitted to ZIMRA.

### Q: What's the difference between zero-rated and exempt taxes?

**A:** Both are 0%, but:
- **Zero-Rated**: Used for exports, VAT recovery allowed
- **Exempt**: Used for education/health, VAT recovery NOT allowed
- Functionally, FiscGuy treats both as 0% tax

### Q: How do I handle multi-currency transactions?

**A:** Set `currency` field per receipt (USD or ZWG). Counters are tracked separately by currency.

### Q: Can I edit receipts after submission?

**A:** No, issued receipts are immutable per ZIMRA spec. Issue a credit note to refund/adjust.

### Q: Where are QR codes stored?

**A:** In the `media/Zimra_qr_codes/` directory (configurable via Django settings). Also accessible via API in `receipt.qr_code`.

### Q: What's the transaction ID (zimra_inv_id)?

**A:** The ID assigned by ZIMRA during submission. Use this to match receipts in ZIMRA reports.

### Q: How do I check remaining API rate limits?

**A:** FiscGuy doesn't enforce limits, but ZIMRA may. Check ZIMRA documentation or contact support.

### Q: Is there a webhook for receipt updates?

**A:** No, poll the API: `GET /api/receipts/` or `GET /api/receipts/{id}/`

### Q: Can I use FiscGuy with asyncio/celery?

**A:** Yes, but ensure database transactions are atomic. See ARCHITECTURE.md for transaction patterns.

---

## Getting Help

- **Documentation:** See ARCHITECTURE.md for technical details
- **Issues:** https://github.com/digitaltouchcode/fisc/issues
- **Email:** cassymyo@gmail.com
- **Examples:** See `fiscguy/tests/` for test cases

---

## License

MIT License - See LICENSE file for details

---

**Last Updated:** April 2026  
**Version:** 0.1.6  
**Maintainers:** Casper Moyo (@cassymyo)
