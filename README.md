# FiscGuy 

[![Tests](https://github.com/digitaltouchcode/fisc/actions/workflows/tests.yml/badge.svg?branch=release)](https://github.com/digitaltouchcode/fisc/actions/workflows/tests.yml?query=branch%3Arelease)
[![Release](https://github.com/digitaltouchcode/fisc/actions/workflows/release.yml/badge.svg?branch=release)](https://github.com/digitaltouchcode/fisc/actions/workflows/release.yml?query=branch%3Arelease)


A Python library for integrating with ZIMRA (Zimbabwe Revenue Authority) fiscal devices. Provides a simple, Pythonic API for managing fiscal operations including device registration, receipt generation, and fiscal day management.

## Features

- Secure Device Integration - Certificate-based authentication with ZIMRA FDMS
- Receipt Management - Create and submit receipts with multiple tax types
- Fiscal Day Operations - Open and close fiscal days with automatic counter management
- Device Status - Query device status and configuration
- Configuration Management - Fetch and manage device configuration
- Tax Support - Supports standard, zero-rated, exempt, and withholding taxes
- Fully Tested - Comprehensive unit tests with 90%+ code coverage

## Installation

```bash
pip install fiscguy
```

Or from source:

```bash
git clone https://github.com/cassymyo-spec/zimra.git
cd zimra
pip install -e .
```

## Quick Start

### Important: Register a Device First

Before using Fiscguy, you must register and initialize a fiscal device:

```bash
python manage.py init_device
```

This interactive command will guide you through:
- Device information entry
- Certificate generation
- Device registration with ZIMRA
- Configuration and tax synchronization

### Important: Environment Switching

When running `python manage.py init_device`:

**If switching FROM TEST TO PRODUCTION:**
- **Safe to proceed** - All test data will be automatically deleted
- The command will warn you and require confirmation (`YES`)
- **All the following test data will be permanently deleted:**
  - Fiscal Days
  - Fiscal Counters
  - Receipts & Receipt Lines
  - Device Configuration
  - Certificates
  - Device record itself
  - Taxes

**If switching FROM PRODUCTION TO TEST:**
- **NOT ADVISABLE** - This will delete your production records
- Only do this if you're absolutely sure you want to lose all production data
- The command will warn you and require confirmation (`YES`)

**How to switch safely:**
1. Run `python manage.py init_device`
2. Answer the environment question (yes=production, no=test)
3. If different from current environment, you'll see a warning
4. Review the warning carefully
5. Type `YES` to confirm deletion and switch

### Using Fiscguy with Django REST Framework

Fiscguy is built as a Django REST Framework-first library. After device registration, integrate it into your Django project:

#### Important: First Sale Automatically Opens Fiscal Day

When you submit your first receipt without an open fiscal day, Fiscguy will **automatically open a new fiscal day**. This means:

- You don't need to manually call `open_day()` before submitting the first receipt
- The fiscal day will be opened silently and a 5-second delay is applied for ZIMRA processing
- Subsequent receipts will use the already-open fiscal day
- You only need to call `close_day()` when you're done with sales for the day

**Example Flow:**
```
1. Submit first receipt → Fiscal day automatically opens
2. Submit more receipts → Use the same open fiscal day
3. Call close_day() → Close the fiscal day when done
```

#### 1. Add to Django Settings

```python
# settings.py
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    'rest_framework',
    'fiscguy',  # Add fiscguy here
]
```

#### 2. Make Migrations

Create migration files for fiscguy models:

```bash
python manage.py makemigrations fiscguy
```

#### 3. Migrate the Database

Apply migrations to your database:

```bash
python manage.py migrate fiscguy
```

#### 4. Include fiscguy URLs in Your Project

Add fiscguy URL endpoints to your Django project:

```python
# urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('fiscguy.urls')),  # Add this line
]
```

#### 5. Access API Endpoints

Fiscguy provides the following REST API endpoints:

- `POST /api/open_day/` - Open a new fiscal day
- `POST /api/close_day/` - Close the current fiscal day
- `POST /api/receipts/` - Create and submit a receipt
- `GET /api/status/` - Get device and fiscal status
- `GET /api/configuration/` - Get device configuration
- `GET /api/taxes/` - Get available tax types
- `GET /api/receipts/` - List all receipts
- `GET /api/receipts/{id}/` - Get receipt details

#### Example API Requests

## Notes on Credit and Debit Notes
- A person can also submit a credit note.
- Debit notes are not mandatory.
- A credit note can have negative values.

**Submit a Receipt:**
```bash
curl -X POST http://localhost:8000/api/receipts/ \
  -H "Content-Type: application/json" \
  -d '{
    "receipt_type": "fiscalinvoice",
    "currency": "USD",
    "total_amount": "100.00",
    "payment_terms": "cash",
    "lines": [
      {
        "product": "Test Item",
        "quantity": 1,
        "unit_price": "100.00",
        "line_total": "100.00",
        "tax_name": "standard rated 15.5%"
      }
    ]
  }'
```

**Submit a Credit Note:**
```bash
curl -X POST http://localhost:8000/api/receipts/ \
  -H "Content-Type: application/json" \
  -d '{
    "receipt_type": "creditnote",
    "credit_note_reference": "R-00001" # the receipt you want to raise a credit note on. It must exists both in fiscguy and zimra,
    "credit_note_reason": "discount",
    "currency": "USD",
    "total_amount": "-100.00",
    "payment_terms": "cash",
    "lines": [
      {
        "product": "Test Item",
        "quantity": 1,
        "unit_price": "-100.00",
        "line_total": "-100.00",
        "tax_name": "standard rated 15.5%"
      }
    ]
  }'
```

**Open a Fiscal Day:**
```bash
curl -X POST http://localhost:8000/api/open_day/ \
  -H "Content-Type: application/json"
```

**Get Device Status:**
```bash
curl -X GET http://localhost:8000/api/status/ \
  -H "Content-Type: application/json"
```

## Models

Fiscguy provides Django ORM models for:

- Device - Fiscal device information
- FiscalDay - Fiscal day records
- FiscalCounter - Receipt counters for fiscal days
- Receipt - Receipt records
- ReceiptLine - Individual receipt line items
- Taxes - Tax type definitions
- Configuration - Device configuration
- Certs - Device certificates and keys
- Buyer - Buyer/customer information

## Error Handling

```python
from fiscguy import submit_receipt
from rest_framework.exceptions import ValidationError

try:
    result = submit_receipt(receipt_data)
except ValidationError as e:
    print(f"Validation error: {e.detail}")
except RuntimeError as e:
    print(f"Runtime error: {e}")
```

## Testing

```bash
# All tests
pytest

# With coverage
pytest --cov=fiscguy

# Specific test
pytest fiscguy/tests/test_api.py::SubmitReceiptTest::test_submit_receipt_success
```

## Development

```bash
# Clone and setup
git clone https://github.com/cassymyo-spec/zimra.git
cd zimra
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Code formatting
black fiscguy
isort fiscguy

# Linting
flake8 fiscguy
pylint fiscguy

# Type checking
mypy fiscguy
```

## Architecture

```
Public API (api.py)
- open_day, close_day, submit_receipt, etc.
         |
Services Layer
- ReceiptService
- ClosingDayService
         |
Handler Layer
- ZIMRAReceiptHandler
         |
Client Layer
- ZIMRAClient (FDMS API)
- ZIMRACrypto (Signing)
```

## Key Components

- fiscguy/api.py - Public library interface (6 functions)
- fiscguy/services/ - Business logic (ReceiptService, ClosingDayService)
- fiscguy/zimra_base.py - ZIMRA FDMS HTTP client
- fiscguy/zimra_receipt_handler.py - Receipt formatting and signing
- fiscguy/zimra_crypto.py - Cryptographic operations
- fiscguy/models.py - Django ORM models
- fiscguy/serializers.py - DRF serializers
- fiscguy/tests/ - Unit tests (22+ tests)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add/adjust tests
4. Submit a PR

See CONTRIBUTING.md for detailed guidelines.

## License

MIT License

## Support

- Email: cassymyo@gmail.com
- Issues: https://github.com/cassymyo-spec/zimra/issues
- Documentation: See README.md, INSTALL.md
