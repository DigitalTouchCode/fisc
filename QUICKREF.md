# Fiscguy Quick Reference

## Installation

```bash
pip install fiscguy
```

## Quick Start (Copy & Paste)

```python
from fiscguy import open_day, close_day, submit_receipt

# 1. Open fiscal day
open_day()

# 2. Submit receipt
receipt = submit_receipt({
    'receipt_type': 'fiscalinvoice',
    'currency': 'USD',
    'total_amount': '100.00',
    'payment_terms': 'cash',
    'lines': [
        {
            'product': 'Item',
            'quantity': '1',
            'unit_price': '100.00',
            'line_total': '100.00',
            'tax_amount': '15.50',
            'tax_name': 'standard rated 15.5%',
        }
    ],
    'buyer': 1,
})

# 3. Close fiscal day
close_day()
```

## Public API Functions

### `open_day()`
- Opens a new fiscal day
- Returns: `{'fiscal_day_number': 1, 'fiscal_day_date': '2026-02-08', ...}`

### `close_day()`
- Closes current fiscal day
- Returns: `{'signature': '...', 'closing_string': '...', ...}`

### `submit_receipt(data)`
- Creates and submits receipt
- Parameters: Receipt dictionary (see below)
- Returns: `{'receiptID': 'XXX', 'receipt_data': {...}}`

### `get_status()`
- Gets device and fiscal status
- Returns: `{'device_id': '...', 'counter': 123, 'fiscal_day': 1, ...}`

### `get_configuration()`
- Fetches device configuration
- Returns: `{'tin': '...', 'business_name': '...', ...}`

### `get_taxes()`
- Gets available tax types
- Returns: `[{'code': '517', 'name': 'standard rated 15.5%', 'percent': 15.5, ...}]`

## Receipt Data Structure

```python
{
    # Required fields
    'receipt_type': 'fiscalinvoice',      # or 'creditnote', 'debitnote'
    'currency': 'USD',                     # Currency code
    'total_amount': '100.00',              # Total amount
    'payment_terms': 'cash',               # cash
    'buyer': 1,                            # Buyer ID
    
    # Line items (required, at least 1)
    'lines': [
        {
            'product': 'Product name',
            'quantity': '1',
            'unit_price': '100.00',
            'line_total': '100.00',
            'tax_amount': '15.50', # optional or 0
            'tax_name': 'standard rated 15.5%',  
        }
    ],
    
    # Optional (for credit notes)
    'credit_note_reference': 'R-000123',   # Original receipt number
    'credit_note_reason': 'cancel',        # Reason for credit
}
```

## Error Handling

```python
from rest_framework.exceptions import ValidationError
from fiscguy import submit_receipt

try:
    receipt = submit_receipt(data)
except ValidationError as e:
    print(f"Validation error: {e.detail}")
except RuntimeError as e:
    print(f"Runtime error: {e}")
```

## Common Errors & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `No Device found` | Device not registered | Run `python manage.py init_device` |
| `Tax with name 'X' not found` | Invalid tax name | Check `get_taxes()` for valid names |
| `No open fiscal day` | Day not opened | Call `open_day()` first |
| `Certificate error` | Bad cert | Re-run `python manage.py init_device` |

## REST API Endpoints (if using Django)

```bash
# Open fiscal day
GET /fiscguy/open-day/

# Close fiscal day
GET /fiscguy/close-day/

# Get status
GET /fiscguy/get-status/

# Get configuration
GET /fiscguy/configuration/

# Get taxes
GET /fiscguy/taxes/

# Submit receipt
POST /fiscguy/receipts/
Content-Type: application/json

{
  "receipt_type": "fiscalinvoice",
  "currency": "USD",
  ...
}

# Retrieve receipt
GET /fiscguy/receipts/{id}/
```

## Django Setup

```python
# settings.py
INSTALLED_APPS = [
    ...
    'fiscguy',
    'rest_framework',
]
```

```bash
# Migrations
python manage.py migrate fiscguy

# Device setup
python manage.py init_device
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

# Format code
black fiscguy
isort fiscguy

# Lint
flake8 fiscguy
```

## Available Tax Types (Examples)

```python
# Standard tax
'tax_name': 'standard rated 15.5%'

# Zero tax
'tax_name': 'zero rated 0%'

# Exempt
'tax_name': 'exempt'

# Withholding
'tax_name': 'withholding'
```

Check available taxes:
```python
from fiscguy import get_taxes

taxes = get_taxes()
for tax in taxes:
    print(f"{tax['name']}: {tax['percent']}%")
```

## Models (Django ORM)

```python
from fiscguy.models import (
    Device, FiscalDay, Receipt, ReceiptLine,
    Taxes, Configuration, Buyer, Certs, FiscalCounter
)

# Example: Get all receipts
receipts = Receipt.objects.all()

# Get specific receipt
receipt = Receipt.objects.get(id=1)
receipt.lines.all()

# Get taxes
taxes = Taxes.objects.all()

# Get device
device = Device.objects.first()
```

## Serializers (DRF)

```python
from fiscguy.serializers import (
    ReceiptSerializer, ReceiptCreateSerializer,
    TaxesSerializer, ConfigurationSerializer
)

# Use ReceiptCreateSerializer for POST (write)
serializer = ReceiptCreateSerializer(data=request.data)

# Use ReceiptSerializer for GET (read)
serializer = ReceiptSerializer(receipt)
```

## Logging

Fiscguy uses loguru for logging:

```python
from loguru import logger

# Logs are automatically generated by library
# Check logs for debugging:
# - Receipt submission
# - Tax resolution
# - Counter updates
# - ZIMRA communication
```

## Documentation & Links

| Resource | Link |
|----------|------|
| **README** | Project overview & API reference |
| **INSTALL** | Setup and configuration guide |
| **CONTRIBUTING** | Development guidelines |
| **STRUCTURE** | Project architecture |
| **CHANGELOG** | Version history |
| **GitHub** | https://github.com/cassymyo-spec/zimra |

## Version

```python
import fiscguy
# Version: 0.1.0 (2026-02-08)
```

## Support

- **Email:** cassymyo@gmail.com
- **Issues:** https://github.com/cassymyo-spec/zimra/issues
- **Docs:** See README, INSTALL, CONTRIBUTING

---

**Last Updated:** 2026-02-08  
**Status:** Production Ready
