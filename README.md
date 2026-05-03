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
- **Online FDMS submission** — receipts are validated, signed, and submitted directly to FDMS
- **Certificate management** — CSR generation, device registration, certificate renewal via `init_device`
- **Multi-currency** — USD and ZWG support with per-currency counter tracking
- **Multiple payment methods** — Cash, Card, Mobile Wallet, Bank Transfer, Coupon, Credit, Other
- **Buyer management** — optional buyer TIN and registration data on receipts
- **Cursor pagination** — efficient receipt listing for large datasets
- **Protected key storage** — device private keys are encrypted at rest
- **Operational hardening** — certificate material is redacted in Django admin and temporary PEM files are cleaned up after use
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
            "hs_code": "99001000",
            "tax_id": 517,
            "quantity": "1",
            "unit_price": "115.00",
            "line_total": "115.00",
            "tax_amount": "15.00",
        }
    ],
})

close_day()
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

### Close-Day Status Flow

Closing a fiscal day has two states to track:

- **Local database state** - `open`, `close_pending`, `close_failed`, `closed`
- **FDMS state** - values such as `FiscalDayOpen`, `FiscalDayCloseInitiated`, `FiscalDayClosed`

FiscGuy does **not** mark the fiscal day closed locally on the first close request. When FDMS
accepts the request with `FiscalDayCloseInitiated`, the library keeps the local day in
`close_pending`, starts background status polling, and only marks the day `closed` after FDMS
confirms the close.

Typical user-facing messages are:

- `Close request submitted. FDMS is processing the fiscal day close.`
- `Closing fiscal day... waiting for FDMS confirmation.`
- `Fiscal day closed successfully.`
- `Fiscal day close failed in FDMS.`

For frontend integrations, call `POST /fiscguy/close-day/` once, then poll
`GET /fiscguy/get-status/` until the fiscal day moves from `close_pending` to `closed` or
`close_failed`.

### HS Code Mapping

FiscGuy supports `hs_code` on receipt lines and passes it through to FDMS as
`receiptLineHSCode`.

Firms should map their product and service catalogues to the correct FDMS-compatible HS codes
before going live. In practice, this means:

- Physical goods should use the applicable tariff / HS classification for that item
- Services and intangible supplies should use the appropriate ZIMRA service classifications where applicable
- HS codes should be maintained as product master data, not typed ad hoc at the point of sale

Recommended approach:

- Add `hs_code` to each product or service in your own catalogue
- Copy that code into each receipt line when submitting receipts
- Reuse the original receipt line HS code for credit notes and product-linked debit notes where possible

Current behavior:

- `fiscalinvoice` lines accept `hs_code` in the payload and send it to FDMS as `receiptLineHSCode`
- `creditnote` lines can inherit `hs_code` from the referenced original receipt line when no
  explicit line `hs_code` is provided
- `debitnote` lines can inherit `hs_code` from the referenced original receipt line, or fall back
  to the appropriate ZIMRA service code when the debit line is a service/intangible adjustment

Example receipt line:

```json
{
  "product": "Consulting Service",
  "hs_code": "99001000",
  "tax_id": 517,
  "quantity": "1",
  "unit_price": "115.00",
  "line_total": "115.00",
  "tax_amount": "15.00"
}
```

Use `GET /fiscguy/taxes/` to fetch the active device tax table first, then submit the
matching `tax_id` on each receipt line. Do not rely on tax-name strings in production payloads.

### Security

FiscGuy includes baseline protections for certificate and signing material:

- Device private keys are encrypted at rest in the `Certs` table
- Raw certificate and private-key fields are not exposed through the default Django admin registration
- Temporary PEM files used for mutual TLS are written with restricted permissions and cleaned up after use
- Dependency versions are maintained against known vulnerability advisories

For production deployments, you should still review application-level authentication,
admin access, database encryption policy, backup handling, and key-management requirements
for your environment.

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

Interactive device setup for first-time provisioning:

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

Dependency audit:

```bash
pip-audit -r requirements.txt
```

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
| [`docs/changelog.md`](docs/changelog.md) | Version history |
| [`docs/contributing.md`](docs/contributing.md) | Contributing guidelines |

---

## Contributing

Contributions are welcome. Please read [`docs/contributing.md`](docs/contributing.md) first.

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
Developed by <a href="mailto:cassymyo@gmail.com">Casper Moyo</a>
</div>
