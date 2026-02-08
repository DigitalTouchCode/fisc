# Fiscguy

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

### Using the Library

Once your device is registered, you can use the library:

```python
from fiscguy import (
    open_day,
    close_day,
    submit_receipt,
    get_status,
    get_configuration,
    get_taxes,
)

# Check device status
status = get_status()
print(f"Device: {status['device_id']}, Counter: {status['counter']}")

# Open a fiscal day
result = open_day()
print(f"Day opened: {result['fiscal_day_number']}")

# Submit a receipt
receipt_data = {
    "receipt_type": "fiscalinvoice",
    "currency": "USD",
    "total_amount": "100.00",
    "payment_terms": "cash",
    "lines": [
        {
            "product": "Test Item",
            "quantity": "1",
            "unit_price": "100.00",
            "line_total": "100.00",
            "tax_amount": "15.50",
            "tax_name": "standard rated 15.5%",
        }
    ],
    "buyer": 1,
}

result = submit_receipt(receipt_data)
print(f"Receipt submitted: {result['receiptID']}")

# Close the fiscal day
result = close_day()
print(f"Day closed, signature: {result['signature'][:20]}...")
```

## API Reference

### `open_day() -> Dict[str, Any]`

Open a new fiscal day.

**Returns:**
- `fiscal_day_number`: The fiscal day number
- `fiscal_day_date`: The date the day was opened (ISO format)
- `message`: Status message (if day already open)

**Raises:**
- `RuntimeError`: If no device is registered

### `close_day() -> Dict[str, Any]`

Close the currently open fiscal day.

**Returns:**
- `signature`: Device signature for the fiscal day
- `closing_string`: Raw closing day string

**Raises:**
- `RuntimeError`: If no device or no open fiscal day exists

### `submit_receipt(receipt_data: Dict[str, Any]) -> Dict[str, Any]`

Create and submit a receipt to ZIMRA.

**Parameters:**
- `receipt_data`: Receipt dictionary with required fields:
  - `receipt_type`: "fiscalinvoice" or "creditnote"
  - `currency`: "USD", "ZWL", etc.
  - `total_amount`: Total amount (string or Decimal)
  - `payment_terms`: "cash", "cheque", "card", etc.
  - `lines`: List of line items
  - `buyer`: Buyer ID (integer)

**Line Item Structure:**
```python
{
    "product": "Product name",
    "quantity": "1",
    "unit_price": "100.00",
    "line_total": "100.00",
    "tax_amount": "15.50",
    "tax_name": "standard rated 15.5%",
}
```

**Returns:**
- `receiptID`: ZIMRA receipt ID
- `receipt_data`: Full receipt data

**Raises:**
- `ValidationError`: If tax_name doesn't match any database tax
- `RuntimeError`: If submission to ZIMRA fails

### `get_status() -> Dict[str, Any]`

Get current device and fiscal status.

**Returns:**
- `device_id`: Device identifier
- `counter`: Global receipt counter
- `fiscal_day`: Current fiscal day number (or null if none open)
- `fiscal_day_status`: Status of fiscal day

### `get_configuration() -> Dict[str, Any]`

Fetch device configuration from the database.

**Returns:**
- Dictionary with configuration fields
- Empty dict if no configuration exists

### `get_taxes() -> List[Dict[str, Any]]`

Fetch all configured tax types.

**Returns:**
- List of tax dictionaries with fields: `code`, `name`, `percent`, `tax_id`

## Django Integration

Fiscguy is built on Django ORM. To use in a Django project:

1. Add to `INSTALLED_APPS` in settings:

```python
INSTALLED_APPS = [
    ...
    "fiscguy",
    "rest_framework",
]
```

2. Run migrations:

```bash
python manage.py migrate fiscguy
```

3. Initialize a device:

```bash
python manage.py init_device
```

4. Use the library:

```python
from fiscguy import open_day, submit_receipt
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

- Email: fiscal@example.com
- Issues: https://github.com/cassymyo-spec/zimra/issues
- Documentation: See README.md, INSTALL.md, QUICKREF.md

## Changelog

### 0.1.0 (2026-02-08)

**Initial Release**

- Public library API with 6 core functions
- Receipt creation and submission
- Fiscal day management
- Device status and configuration
- Tax type management
- 22+ comprehensive unit tests
- Full error handling and logging
- Lazy-loaded module caching
