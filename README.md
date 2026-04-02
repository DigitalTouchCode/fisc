<div align="center">

# FiscGuy

[![Tests](https://github.com/digitaltouchcode/fisc/actions/workflows/tests.yml/badge.svg?branch=release)](https://github.com/digitaltouchcode/fisc/actions/workflows/tests.yml?query=branch%3Arelease)
[![PyPI version](https://img.shields.io/pypi/v/fiscguy.svg?v=1)](https://pypi.org/project/fiscguy/)
[![Downloads](https://static.pepy.tech/badge/fiscguy)](https://pepy.tech/project/fiscguy)
![Python](https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13-blue)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**The Modern Python Library for ZIMRA Fiscal Device Integration**

FiscGuy gives Django applications a simple, Pythonic interface for every fiscal operation required by the Zimbabwe Revenue Authority — receipt submission, fiscal day management, certificate handling, and more. Built on Django REST Framework, it drops into any Django project in minutes.

[Installation](#installation) • [Quick Start](#quick-start) • [API Reference](#api-reference) • [REST Endpoints](#rest-endpoints) • [Docs](#documentation) • [Contributing](#contributing)

---

</div>

## Features

- **Six core API functions** — `open_day`, `close_day`, `submit_receipt`, `get_status`, `get_configuration`, `get_taxes`
- **Full fiscal day lifecycle** — open, manage counters, close with ZIMRA-compliant hash and signature
- **Receipt types** — Fiscal Invoice, Credit Note, Debit Note with correct counter tracking
- **Certificate management** — CSR generation, device registration, certificate renewal via `init_device`
- **Multi-currency** — USD and ZWG support with per-currency counter tracking
- **Multiple payment methods** — Cash, Card, Mobile Wallet, Bank Transfer, Coupon, Credit, Other
- **Buyer management** — optional buyer TIN and registration data on receipts
- **Cursor pagination** — efficient receipt listing for large datasets
- **Typed exceptions** — every error condition has its own exception class
- **90%+ test coverage** — mocked ZIMRA and crypto, fast CI

---

## Requirements

- Python 3.11, 3.12, or 3.13
- Django 4.2+
- Django REST Framework 3.14+

---

## Installation

```bash
pip install fiscguy
```

### From source

```bash
git clone https://github.com/digitaltouchcode/fisc.git
cd fisc
pip install -e ".[dev]"
```

---

## Quick Start

### 1. Add to Django settings

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "fiscguy",
    "rest_framework",
]
```

### 2. Run migrations

```bash
python manage.py migrate
```

### 3. Initialise your device

```bash
python manage.py init_device
```

This interactive command collects your device credentials, generates a CSR, registers the device with ZIMRA, and fetches taxes and configuration automatically.

### 4. Include URLs

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    path("fiscguy/", include("fiscguy.urls")),
]
```

### 5. Submit your first receipt

```python
from fiscguy import open_day, submit_receipt, close_day

open_day()

receipt = submit_receipt({
    "receipt_type": "fiscalinvoice",
    "currency": "USD",
    "total_amount": "115.00",
    "payment_terms": "Cash",
    "lines": [
        {
            "product": "Consulting Service",
            "quantity": "1",
            "unit_price": "115.00",
            "line_total": "115.00",
            "tax_amount": "15.00",
            "tax_name": "standard rated 15%",
        }
    ],
})

close_day()
```

---

## API Reference

FiscGuy exposes six top-level functions. Import them directly from `fiscguy`:

```python
from fiscguy import open_day, close_day, submit_receipt, get_status, get_configuration, get_taxes
```

### `open_day()`

Opens a new fiscal day. Syncs the `fiscalDayNo` from FDMS and fetches the latest configuration and taxes.

```python
from fiscguy import open_day

result = open_day()
# {"fiscalDayNo": 42, "fiscalDayOpened": "2026-03-30T08:00:00"}
```

**Raises:** `FiscalDayError` if a day is already open or FDMS rejects the request.

---

### `submit_receipt(receipt_data)`

Validates, signs, and submits a receipt to ZIMRA FDMS. Increments fiscal counters. If FDMS is offline, the receipt is saved locally and queued for automatic sync.

```python
from fiscguy import submit_receipt

receipt = submit_receipt({
    "receipt_type": "fiscalinvoice",   # fiscalinvoice | creditnote | debitnote
    "currency": "USD",                 # USD | ZWG
    "total_amount": "115.00",
    "payment_terms": "Cash",           # Cash | Card | MobileWallet | BankTransfer | Coupon | Credit | Other
    "lines": [
        {
            "product": "Item name",
            "quantity": "2",
            "unit_price": "57.50",
            "line_total": "115.00",
            "tax_amount": "15.00",
            "tax_name": "standard rated 15%",
        }
    ],
    # Optional
    "buyer": {
      "name": "Tendai Nyathi",
      "trade_name": "Nyathi Hardware",
      "address": "45 Samora Machel Avenue, Harare",
      "phonenumber": "0773124567",
      "tin_number": "2045678912",
      "email": "tendai.nyathi@example.com"
    },                        # Buyer model ID
    "credit_note_reason": "...",       # Required for creditnote
    "credit_note_reference": "R-...", # Required for creditnote — original receipt number
})
```

**Returns:** Serialized receipt data including `receipt_number`, `qr_code`, `hash_value`, and `zimra_inv_id`.

**Raises:** `ReceiptSubmissionError` on any processing or FDMS failure.

---

### `close_day()`

Builds the fiscal day closing string, signs it with the device private key, and submits it to ZIMRA. Marks the fiscal day as closed in the database.

```python
from fiscguy import close_day

result = close_day()
# {"fiscalDayStatus": "FiscalDayClosed", ...}
```

**Raises:** `CloseDayError` if FDMS rejects the request (e.g. `CountersMismatch`, `BadCertificateSignature`).

---

### `get_status()`

Fetches the current device and fiscal day status from FDMS.

```python
from fiscguy import get_status

status = get_status()
# {"fiscalDayStatus": "FiscalDayOpened", "lastReceiptGlobalNo": 142, ...}
```

---

### `get_configuration()`

Returns the stored taxpayer configuration.

```python
from fiscguy import get_configuration

config = get_configuration()
# {"tax_payer_name": "ACME Ltd", "tin_number": "...", ...}
```

---

### `get_taxes()`

Returns all configured tax types.

```python
from fiscguy import get_taxes

taxes = get_taxes()
# [{"tax_id": 1, "name": "Exempt", "percent": "0.00"}, ...]
```

---

## REST Endpoints

When URLs are included, FiscGuy exposes the following endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/fiscguy/open-day/` | Open a new fiscal day |
| `POST` | `/fiscguy/close-day/` | Close the current fiscal day |
| `GET` | `/fiscguy/get-status/` | Get device and fiscal day status |
| `POST` | `/fiscguy/get-ping/` | Ping FDMS to report device is online |
| `GET` | `/fiscguy/receipts/` | List receipts (cursor paginated) |
| `POST` | `/fiscguy/receipts/` | Submit a new receipt |
| `GET` | `/fiscguy/receipts/{id}/` | Retrieve a receipt by ID |
| `GET` | `/fiscguy/configuration/` | Get taxpayer configuration |
| `POST` | `/fiscguy/sync-config/` | Manually sync configuration from FDMS |
| `GET` | `/fiscguy/taxes/` | List all tax types |
| `POST` | `/fiscguy/issue-certificate/` | Renew device certificate |
| `*` | `/fiscguy/buyer/` | Buyer CRUD (ModelViewSet) |

### Pagination

Receipt listing supports cursor-based pagination:

```
GET /fiscguy/receipts/?page_size=20
```

Default page size: `10`. Maximum: `100`.

---

## Error Handling

All operations raise typed exceptions. Import them from `fiscguy.exceptions`:

```python
from fiscguy.exceptions import (
    ReceiptSubmissionError,
    CloseDayError,
    FiscalDayError,
    ConfigurationError,
    CertificateError,
    DevicePingError,
    StatusError,
)

try:
    close_day()
except CloseDayError as e:
    print(f"Close day failed: {e}")
```

| Exception | Raised when |
|-----------|-------------|
| `ReceiptSubmissionError` | Receipt processing or FDMS submission fails |
| `CloseDayError` | FDMS rejects the close day request |
| `FiscalDayError` | Fiscal day cannot be opened or is already open |
| `ConfigurationError` | Configuration is missing or sync fails |
| `CertificateError` | Certificate issuance or renewal fails |
| `DevicePingError` | Ping to FDMS fails |
| `StatusError` | Status fetch from FDMS fails |
| `DeviceRegistrationError` | Device registration with ZIMRA fails |
| `CryptoError` | RSA signing or hashing fails |

---

## Models

FiscGuy adds the following tables to your database:

| Model | Description |
|-------|-------------|
| `Device` | Fiscal device registration details |
| `Configuration` | Taxpayer configuration synced from FDMS |
| `Certs` | Device certificate and private key |
| `Taxes` | Tax types synced from FDMS on day open |
| `FiscalDay` | Daily fiscal period with receipt counter |
| `FiscalCounter` | Running totals per tax / payment method |
| `Receipt` | Submitted receipts with hash, signature, QR code |
| `ReceiptLine` | Individual line items on a receipt |
| `Buyer` | Optional buyer registration data |

Access them directly:

```python
from fiscguy.models import Device, Receipt, FiscalDay, Taxes

device = Device.objects.first()
open_days = FiscalDay.objects.filter(is_open=True)
receipts = Receipt.objects.select_related("buyer").prefetch_related("lines")
```

---

## Management Commands

### `init_device`

Interactive device setup — run once per device:

```bash
python manage.py init_device
```

The command will:
1. Prompt for `org_name`, `activation_key`, `device_id`, `device_model_name`, `device_model_version`, `device_serial_number`
2. Ask whether to use production or testing FDMS
3. Generate an RSA key pair and CSR
4. Register the device with ZIMRA to obtain a signed certificate
5. Fetch and persist configuration and taxes

---

## Testing
## Testing

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=fiscguy --cov-report=html

# Run a specific test file
pytest fiscguy/tests/test_views.py

# Run a specific test
pytest fiscguy/tests/test_closing_day_service.py::TestBuildSaleByTax
```

All tests mock ZIMRA API calls and crypto operations — no network access required.

---

## Documentation

Full documentation lives in the `docs/` folder:

| Document | Description |
|----------|-------------|
| [`docs/installation.md`](docs/installation.md) | Detailed installation and setup guide |
| [`docs/receipt-types.md`](docs/receipt-types.md) | Fiscal Invoice, Credit Note, Debit Note rules |
| [`docs/fiscal-counters.md`](docs/fiscal-counters.md) | How counters work and how they are calculated |
| [`docs/closing-day.md`](docs/closing-day.md) | Closing day hash string and signature spec |
| [`docs/certificate-management.md`](docs/certificate-management.md) | Certificate lifecycle and renewal |
| [`docs/error-reference.md`](docs/error-reference.md) | All exceptions and what causes them |
| [`CHANGELOG.md`](CHANGELOG.md) | Version history |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contributing guidelines |

---

## Contributing

Contributions are welcome. Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) first.

```bash
# Set up dev environment
git clone https://github.com/digitaltouchcode/fisc.git
cd fisc
pip install -e ".[dev]"
pre-commit install

# Before submitting a PR
black fiscguy
isort fiscguy
flake8 fiscguy
pytest
```

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">
Built for Zimbabwe 🇿🇼 by <a href="https://github.com/digitaltouchcode">Digital Touch Code</a>
</div>
