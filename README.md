<div align="center">

# FiscGuy

[![Tests](https://github.com/digitaltouchcode/fisc/actions/workflows/tests.yml/badge.svg?branch=release)](https://github.com/digitaltouchcode/fisc/actions/workflows/tests.yml?query=branch%3Drelease)
[![PyPI version](https://img.shields.io/pypi/v/fiscguy.svg?v=1)](https://pypi.org/project/fiscguy/)
[![Downloads](https://static.pepy.tech/badge/fiscguy)](https://pepy.tech/project/fiscguy)
![Python](https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13-blue)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**The Modern Python Library for ZIMRA Fiscal Device Integration**

FiscGuy gives Django applications a simple, Pythonic interface for every fiscal operation required by the Zimbabwe Revenue Authority — receipt submission, fiscal day management, certificate handling, and more. Built on Django REST Framework, it drops into any Django project in minutes.

[Installation](#installation) • [Quick Start](#quick-start) • [API Reference](#api-reference) • [REST Endpoints](#rest-endpoints) • [📚 Full Documentation](https://digitaltouchcode.github.io/fisc/) • [Contributing](#contributing)

---

</div>

## Features

- **Seven core API functions** — `open_day`, `close_day`, `submit_receipt`, `get_status`, `get_configuration`, `get_taxes`, `get_buyer`
- **Full fiscal day lifecycle** — open, manage counters, close with ZIMRA-compliant hash and signature
- **Receipt types** — Fiscal Invoice, Credit Note, Debit Note with correct counter tracking
- **Offline resilience** — receipts queued locally when FDMS is unreachable, synced automatically on reconnect
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
```s
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

## 📚 Documentation

**[📖 View Full Documentation](https://digitaltouchcode.github.io/fisc/)**

Our comprehensive documentation covers everything you need to know:

### 🚀 Quick Links
- **[Installation Guide](https://digitaltouchcode.github.io/fisc/installation/)** - Detailed setup instructions
- **[Receipt Types](https://digitaltouchcode.github.io/fisc/receipt-types/)** - Fiscal Invoice, Credit Note, Debit Note rules
- **[Fiscal Counters](https://digitaltouchcode.github.io/fisc/fiscal-counters/)** - Counter tracking and calculations
- **[Closing Day](https://digitaltouchcode.github.io/fisc/closing-day/)** - Hash string and signature specifications
- **[Certificate Management](https://digitaltouchcode.github.io/fisc/certificate-management/)** - Certificate lifecycle and renewal
- **[Error Reference](https://digitaltouchcode.github.io/fisc/error-reference/)** - All exceptions and troubleshooting

### 🌐 GitHub Pages Setup

This documentation is automatically deployed to GitHub Pages when you push to the `release` branch.

**To enable GitHub Pages:**
1. Go to your repository Settings → Pages
2. Source: Select "GitHub Actions" 
3. The documentation will be available at: `https://digitaltouchcode.github.io/fisc/`

**Manual deployment commands:**
```bash
# Build and deploy locally
./docs-deploy.sh

# Or build only
./docs-build.sh
```

### 📋 Documentation Contents

| Document | Description |
|----------|-------------|
| [Installation](https://digitaltouchcode.github.io/fisc/installation/) | Detailed installation and setup guide |
| [Receipt Types](https://digitaltouchcode.github.io/fisc/receipt-types/) | Fiscal Invoice, Credit Note, Debit Note rules |
| [Fiscal Counters](https://digitaltouchcode.github.io/fisc/fiscal-counters/) | How counters work and how they are calculated |
| [Closing Day](https://digitaltouchcode.github.io/fisc/closing-day/) | Closing day hash string and signature spec |
| [Certificate Management](https://digitaltouchcode.github.io/fisc/certificate-management/) | Certificate lifecycle and renewal |
| [Error Reference](https://digitaltouchcode.github.io/fisc/error-reference/) | All exceptions and what causes them |
| [Changelog](https://digitaltouchcode.github.io/fisc/changelog/) | Version history |
| [Contributing](https://digitaltouchcode.github.io/fisc/contributing/) | Contributing guidelines |

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
Built for Zimbabwe 🇿🇼 by <a href="mailto:cassymyo@gmail.com">Casper Moyo</a>
</div>