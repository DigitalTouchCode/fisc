# Fiscguy Package Installation & Setup Guide

## About Fiscguy

Fiscguy is a Python library for integrating ZIMRA fiscal devices with your Django applications. This guide helps you get started quickly.

## Installation

### Via pip (from PyPI)

```bash
pip install fiscguy
```

### From Source (Development)

```bash
git clone https://github.com/cassymyo-spec/zimra.git
cd zimra
pip install -e .
```

### With Development Dependencies

```bash
pip install -e ".[dev]"  # Includes testing, linting, type checking tools
```

## Quick Setup (5 minutes)

### 1. Add to Django Settings

```python
# settings.py
INSTALLED_APPS = [
    # ...
    'fiscguy',
    'rest_framework',
]

# Optional: Configure fiscal operations
FISCAL_SETTINGS = {
    'ENVIRONMENT': 'test',  # or 'production'
    'TIMEZONE': 'Africa/Harare',
}
```

### 2. Run Migrations

```bash
python manage.py migrate fiscguy
```

### 3. Initialize Device

```bash
python manage.py init_device
```

This interactive command will:
- Prompt for device information
- Generate certificate signing request (CSR)
- Register device with ZIMRA
- Fetch configuration and taxes

### 4. Use the Library

```python
from fiscguy import open_day, submit_receipt, close_day

# Open fiscal day
open_day()

# Submit a receipt
receipt = submit_receipt({
    'receipt_type': 'fiscalinvoice',
    'currency': 'USD',
    'total_amount': '100.00',
    'payment_terms': 'cash',
    'lines': [
        {
            'product': 'Service',
            'quantity': '1',
            'unit_price': '100.00',
            'line_total': '100.00',
            'tax_amount': '15.50',
            'tax_name': 'standard rated 15.5%',
        }
    ],
    'buyer': 1,  # Buyer ID
})

# Close fiscal day
close_day()
```

## API Functions

### Six Core Functions

1. **`open_day()`** - Open a fiscal day
2. **`close_day()`** - Close the current fiscal day
3. **`submit_receipt(receipt_data)`** - Submit a receipt
4. **`get_status()`** - Get device status
5. **`get_configuration()`** - Get device configuration
6. **`get_taxes()`** - Get available tax types

## REST Endpoints (if using Django views)

Fiscguy also provides REST API endpoints:

```
GET  /fiscguy/open-day/         - Open fiscal day
GET  /fiscguy/close-day/        - Close fiscal day
GET  /fiscguy/get-status/       - Get status
POST /fiscguy/receipts/         - Submit receipt
GET  /fiscguy/receipts/{id}/    - Get receipt
GET  /fiscguy/configuration/    - Get configuration
GET  /fiscguy/taxes/            - Get taxes
```

## Database Models

Fiscguy includes these Django models:

- **Device** - Fiscal device info
- **FiscalDay** - Fiscal day records
- **Receipt** - Receipt records
- **ReceiptLine** - Receipt line items
- **Taxes** - Tax types
- **Configuration** - Device configuration
- **Certs** - Device certificates
- **Buyer** - Customer info
- **FiscalCounter** - Receipt counters

Access them:

```python
from fiscguy.models import Device, Receipt, Taxes

device = Device.objects.first()
receipts = Receipt.objects.all()
taxes = Taxes.objects.all()
```

## Configuration

### Environment Variables

```bash
# .env
ZIMRA_ENVIRONMENT=test  # or 'production'
ZIMRA_TIMEOUT=5
DEBUG=True
```

### Django Settings (Optional)

```python
# settings.py
FISCAL_SETTINGS = {
    'ENVIRONMENT': 'test',
    'TIMEOUT': 5,
    'VERIFY_SSL': True,
}
```

## Testing

### Run Unit Tests

```bash
# All tests
pytest

# Specific test
pytest fiscguy/tests/test_api.py::OpenDayTest

# With coverage
pytest --cov=fiscguy --cov-report=html
```

### Mock External Services

Tests automatically mock ZIMRA API calls and crypto operations, so they run fast without network access.

## Error Handling

All API functions raise exceptions on error:

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

## Troubleshooting

### "No Device found"

```
RuntimeError: No Device found. Please run init_device management command.
```

**Solution:** Run device initialization:
```bash
python manage.py init_device
```

### "Tax with name 'X' not found"

```
ValidationError: Tax with name 'X' not found
```

**Solution:** Check available taxes and use exact name:
```python
from fiscguy.models import Taxes
taxes = Taxes.objects.all()
for tax in taxes:
    print(f"{tax.name} - {tax.percent}%")
```

### Certificate Errors

```
MalformedFraming: Unable to load PEM file
```

**Solution:** Re-register device:
```bash
python manage.py init_device
```

### "No open fiscal day"

```
RuntimeError: No open fiscal day
```

**Solution:** Open a fiscal day first:
```python
from fiscguy import open_day
open_day()
```

## Development

### Setting Up Development Environment

```bash
# Clone repo
git clone https://github.com/cassymyo-spec/zimra.git
cd zimra

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install in editable mode with dev tools
pip install -e ".[dev]"

# Install pre-commit hooks (optional)
pre-commit install
```

### Code Quality Checks

```bash
# Format code
black fiscguy
isort fiscguy

# Lint
flake8 fiscguy
pylint fiscguy

# Type checking
mypy fiscguy

# Tests
pytest
```

## Documentation

- **README.md** - Project overview and quick start
- **CONTRIBUTING.md** - Contributing guidelines
- **CHANGELOG.md** - Version history
- Inline docstrings - Function documentation
- `fiscguy/api.py` - Public API module

## Next Steps

1. Install fiscguy
2. Run migrations
3. Initialize device
4. Submit your first receipt!
5. Read [API Reference](README.md#api-reference)
6. Check [Contributing Guide](CONTRIBUTING.md)

## Support

- Email: cassymyo@gmail.com
- Report Issues: [GitHub Issues](https://github.com/cassymyo-spec/zimra/issues)
- Discussions: [GitHub Discussions](https://github.com/cassymyo-spec/zimra/discussions)

## License

MIT License - See [LICENSE](LICENSE)

---

**Happy coding with Fiscguy!**
