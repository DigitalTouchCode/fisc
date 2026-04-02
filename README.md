# FiscGuy

<div align="center">

[![Tests](https://github.com/digitaltouchcode/fisc/actions/workflows/tests.yml/badge.svg?branch=release)](https://github.com/digitaltouchcode/fisc/actions/workflows/tests.yml?query=branch%3Arelease)
[![PyPI version](https://img.shields.io/pypi/v/fiscguy.svg?v=1)](https://pypi.org/project/fiscguy/)
[![Downloads](https://static.pepy.tech/badge/fiscguy)](https://pepy.tech/project/fiscguy)
![Python](https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13-blue)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

**The Modern Python Library for ZIMRA Fiscal Device Integration**

Library for integrating with ZIMRA (Zimbabwe Revenue Authority) fiscal devices. Built with Django and Django REST Framework, FiscGuy provides a simple, Pythonic API for managing fiscal operations with enterprise-grade security and reliability.

[Documentation](https://github.com/digitaltouchcode/fisc#documentation) â€¢ [API Reference](#api-endpoints) â€¢ [Contributing](#contributing)

</div>

---

## Features

- **Secure Device Integration** â€” Certificate-based mutual TLS authentication with ZIMRA FDMS
- **Receipt Management** â€” Create, sign, and submit receipts with automatic validation and cryptographic signing
- **Fiscal Day Operations** â€” Automatic fiscal day management with intelligent counter tracking and state management
- **Device Configuration** â€” Sync taxpayer information and tax rates directly from ZIMRA
- **Credit & Debit Notes** â€” Issue refunds and adjustments per ZIMRA specifications
- **Multi-Currency Support** â€” Handle USD and ZWG transactions seamlessly
- **QR Code Generation** â€” Auto-generate verification codes for receipt validation
- **Fully Tested** â€” 90%+ code coverage with 22+ comprehensive test cases
- **Production Ready** â€” Battle-tested in live ZIMRA deployments

---

## Installation

### PyPI

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

## 5-Minute Quick Start

### 1. Add to Django Settings

```python
# settings.py
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'rest_framework',
    'fiscguy',  # <- Add this
]
```

### 2. Run Migrations

```bash
python manage.py migrate fiscguy
```

### 3. Register Your Fiscal Device

```bash
python manage.py init_device
```

This interactive command will guide you through:
- Device information entry
- Certificate generation & registration with ZIMRA
- Configuration and tax synchronization

> **Note:** Environment switching (test <-> production) will delete all existing data in that environment and require confirmation with `YES`.

### 4. Include URLs

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    path('api/', include('fiscguy.urls')),
]
```

### 5. Submit Your First Receipt

```bash
curl -X POST http://localhost:8000/api/receipts/ \
  -H "Content-Type: application/json" \
  -d '{
    "receipt_type": "fiscalinvoice",
    "total_amount": "100.00",
    "currency": "USD",
    "payment_terms": "cash",
    "lines": [{
      "product": "Test Item",
      "quantity": 1,
      "unit_price": "100.00",
      "line_total": "100.00",
      "tax_name": "standard rated 15.5%"
    }]
  }'
```

> **Pro Tip:** First receipt automatically opens a fiscal day! No need to call `/open_day/` manually.

---

## Key Concepts

### Automatic Fiscal Day Opening

When you submit your first receipt without an open fiscal day, FiscGuy automatically opens a new fiscal day in the background:

```
Submit Receipt #1 -> Auto-open Fiscal Day -> Process Receipt -> Automatic 5s ZIMRA delay
Submit Receipt #2 -> Use open Fiscal Day -> Process Receipt
...
Call close_day() -> Close Fiscal Day for the day
```

No manual management needed. Just submit receipts and FiscGuy handles the rest.

### Environment Switching

When switching between test and production environments:

| Scenario | Safe? | Action |
|----------|-------|--------|
| **Test to Production** | Yes | Confirm deletion of test data |
| **Production to Test** | No | Only if you're certain about losing production data |

---

## Usage Examples

### Example 1: Simple Receipt

```python
from fiscguy.models import Device
from rest_framework.test import APIClient

device = Device.objects.first()
client = APIClient()

response = client.post('/api/receipts/', {
    'receipt_type': 'fiscalinvoice',
    'total_amount': '150.00',
    'currency': 'USD',
    'payment_terms': 'Cash',
    'lines': [
        {
            'product': 'Bread',
            'quantity': 2,
            'unit_price': '50.00',
            'line_total': '100.00',
            'tax_name': 'standard rated 15.5%'
        }
    ]
})

print(response.data['receipt_number'])  # R-00000001
print(response.data['zimra_inv_id'])    # ZIM-123456
```

### Example 2: Credit Note (Refund)

```python
response = client.post('/api/receipts/', {
    'receipt_type': 'creditnote',
    'credit_note_reference': 'R-00000001',  # Original receipt
    'credit_note_reason': 'customer_return',
    'total_amount': '-50.00',
    'currency': 'USD',
    'payment_terms': 'Cash',
    'lines': [
        {
            'product': 'Bread (Returned)',
            'quantity': 1,
            'unit_price': '-50.00',
            'line_total': '-50.00',
            'tax_name': 'standard rated 15.5%'
        }
    ]
})
```

### Example 3: Receipt with Buyer Information

```python
response = client.post('/api/receipts/', {
    'receipt_type': 'fiscalinvoice',
    'total_amount': '500.00',
    'currency': 'USD',
    'payment_terms': 'BankTransfer',
    'buyer': {
        'name': 'Tech Solutions Ltd',
        'tin_number': '1234567890',
        'email': 'tech@example.com',
        'address': '123 Tech Park'
    },
    'lines': [
        {
            'product': 'Software License',
            'quantity': 1,
            'unit_price': '500.00',
            'line_total': '500.00',
            'tax_name': 'standard rated 15.5%'
        }
    ]
})
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/receipts/` | `POST` | Create and submit a receipt |
| `/api/receipts/` | `GET` | List all receipts (paginated) |
| `/api/receipts/{id}/` | `GET` | Get receipt details |
| `/api/open-day/` | `POST` | Open a fiscal day |
| `/api/close-day/` | `POST` | Close the current fiscal day |
| `/api/status/` | `GET` | Get device and fiscal status |
| `/api/configuration/` | `GET` | Get device configuration |
| `/api/taxes/` | `GET` | List available taxes |
| `/api/buyer/` | `GET` | List all buyers |
| `/api/buyer/` | `POST` | Create a buyer |

For detailed API documentation, see [USER_GUIDE.md](USER_GUIDE.md#api-endpoints) or [endpoints.md](endpoints.md).

---

## Database Models

FiscGuy provides comprehensive Django ORM models:

- **Device** â€” Fiscal device information and status
- **FiscalDay** â€” Fiscal day records with open/close tracking
- **FiscalCounter** â€” Receipt counters aggregated by type and currency
- **Receipt** â€” Receipt records with automatic signing and ZIMRA tracking
- **ReceiptLine** â€” Line items within receipts
- **Taxes** â€” Tax type definitions synced from ZIMRA
- **Configuration** â€” Device configuration and taxpayer information
- **Certs** â€” Device certificates and cryptographic keys
- **Buyer** â€” Buyer/customer information for receipts

All models are fully documented in [ARCHITECTURE.md](ARCHITECTURE.md#data-models).

---

## Architecture

FiscGuy follows a clean layered architecture:

```
+---------------------------------------------+
|         REST API Layer (views.py)           |
+---------------------------------------------+
|       Service Layer (services/)             |
+---------------------------------------------+
|    Data Layer (models.py, serializers.py)   |
+---------------------------------------------+
|    ZIMRA Integration (zimra_*.py)           |
+-----------------------------+---------------+
                              |
                              v
                       ZIMRA FDMS REST API
```

Key design principles:

- **Separation of Concerns** â€” Clear boundaries between layers
- **Atomic Operations** â€” Database transactions ensure data consistency
- **Cryptographic Security** â€” RSA-2048 signing with SHA-256 hashing
- **ZIMRA Compliance** â€” Fully compliant with ZIMRA FDMS specifications
- **Comprehensive Testing** â€” 90%+ code coverage with 22+ test cases

For complete architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Testing

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=fiscguy --cov-report=html

# Run specific test
pytest fiscguy/tests/test_api.py::SubmitReceiptTest

# Run with verbose output
pytest -v
```

All tests mock external ZIMRA API calls, so they run fast without network dependencies.

---

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/digitaltouchcode/fisc.git
cd fisc

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"
```

### Code Quality

```bash
# Format with Black
black fiscguy

# Sort imports with isort
isort fiscguy

# Lint with flake8
flake8 fiscguy

# Type checking with mypy
mypy fiscguy

# All checks at once
black fiscguy && isort fiscguy && flake8 fiscguy && mypy fiscguy
```

### Project Structure

```
fiscguy/
â”œâ”€â”€ models.py                 # Django ORM models
â”œâ”€â”€ serializers.py            # DRF serializers for validation
â”œâ”€â”€ views.py                  # REST API endpoints
â”œâ”€â”€ zimra_base.py             # ZIMRA FDMS HTTP client
â”œâ”€â”€ zimra_crypto.py           # Cryptographic operations
â”œâ”€â”€ zimra_receipt_handler.py  # Receipt formatting & signing
â”œâ”€â”€ services/                 # Business logic layer
â”‚   â”œâ”€â”€ receipt_service.py
â”‚   â”œâ”€â”€ closing_day_service.py
â”‚   â”œâ”€â”€ configuration_service.py
â”‚   â””â”€â”€ status_service.py
â”œâ”€â”€ management/commands/      # Django management commands
â”‚   â””â”€â”€ init_device.py
â””â”€â”€ tests/                    # Unit tests (22+ test cases)
```

---

## Documentation

FiscGuy has comprehensive documentation for all audiences:

| Document | For | Content |
|----------|-----|---------|
| **[USER_GUIDE.md](USER_GUIDE.md)** | Users & Integrators | Installation, API reference, examples, troubleshooting, FAQ |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | Developers | Technical details, data models, service layer, cryptography |
| **[INSTALL.md](INSTALL.md)** | DevOps & Setup | Detailed installation and configuration |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | Contributors | Development specifications and ERP integration |
| **[DOCS_INDEX.md](DOCS_INDEX.md)** | Everyone | Documentation navigation and quick reference |

Start here: [DOCS_INDEX.md](DOCS_INDEX.md) for guided navigation.

---

## Error Handling

```python
from rest_framework.exceptions import ValidationError
from fiscguy.services.receipt_service import ReceiptService

try:
    service = ReceiptService()
    receipt = service.create_receipt(data)
except ValidationError as e:
    print(f"Validation Error: {e.detail}")
except RuntimeError as e:
    print(f"Runtime Error: {e}")
```

Common exceptions:

- `ValidationError` â€” Invalid input data
- `RuntimeError` â€” No device registered or fiscal day issues
- `ZIMRAException` â€” ZIMRA API communication errors

---

## Contributing

We welcome contributions! Here's how to get started:

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/amazing-feature`
3. **Write** tests for new features
4. **Run** code quality checks: `black . && isort . && flake8 . && mypy .`
5. **Commit** with descriptive messages: `git commit -m "feat: add amazing feature"`
6. **Push** to your fork and **open a PR**

For detailed guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Code Standards

- **Style Guide:** [PEP 8](https://pep8.org/) with [Black](https://github.com/psf/black)
- **Imports:** Sorted with [isort](https://pycqa.github.io/isort/)
- **Linting:** [flake8](https://flake8.pycqa.org/) and [pylint](https://pylint.readthedocs.io/)
- **Type Checking:** [mypy](https://www.mypy-lang.org/)
- **Test Coverage:** 90%+ required
- **Testing Framework:** [pytest](https://pytest.org/)

---

## License

FiscGuy is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

## FAQ

**Q: Do I need to open a fiscal day manually?**  
A: No. FiscGuy automatically opens a fiscal day when you submit your first receipt of the day.

**Q: Can I use FiscGuy without Django?**  
A: FiscGuy is built for Django. If you need a standalone library, check our API layer at `fiscguy/zimra_base.py`.

**Q: What's the difference between receipts, credit notes, and debit notes?**  
A: Receipts are normal sales (positive amount). Credit notes are refunds/returns (negative amount). Debit notes are not mandatory and rarely used.

**Q: How do I handle ZIMRA being offline?**  
A: Receipts are cached locally and automatically submitted when ZIMRA comes back online.

**Q: Can I switch from test to production?**  
A: Yes. Run `python manage.py init_device` and confirm the environment switch. All test data will be deleted.

More FAQs in [USER_GUIDE.md](USER_GUIDE.md#faq).

---

## Support & Community

- **Email:** cassymyo@gmail.com
- **Issues:** [GitHub Issues](https://github.com/digitaltouchcode/fisc/issues)
- **Discussions:** [GitHub Discussions](https://github.com/digitaltouchcode/fisc/discussions)
- **Documentation:** [DOCS_INDEX.md](DOCS_INDEX.md)

---

## Acknowledgments

FiscGuy is built on the excellent Django and Django REST Framework ecosystems. Special thanks to the ZIMRA Authority for the FDMS API specifications.

---

<div align="center">

Made with love by Casper Moyo

[Star us on GitHub](https://github.com/digitaltouchcode/fisc)

</div>
