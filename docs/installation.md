# Installation & Setup

## Requirements

- Python 3.11, 3.12, or 3.13
- Django 4.2+
- Django REST Framework 3.14+

---

## Install

### From PyPI

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

## Django Setup

### 1. Add to `INSTALLED_APPS`

```python
# settings.py
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "fiscguy",
    # ... your apps
]
```

### 2. Run migrations

```bash
python manage.py migrate
```

### 3. Include URLs

```python
# your project urls.py
from django.urls import path, include

urlpatterns = [
    path("fiscguy/", include("fiscguy.urls")),
]
```

### 4. Media files (for QR codes)

FiscGuy saves receipt QR codes to `MEDIA_ROOT`. Configure it in settings:

```python
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```

And serve media in development:

```python
# urls.py
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    ...
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

---

## Device Initialisation

Run once per device. This is the most important setup step:

```bash
python manage.py init_device
```

You will be prompted for:

| Prompt | Example | Description |
|--------|---------|-------------|
| Organisation name | `Cas Bz` | Your company name |
| Activation key | `ABC-123-XYZ` | Provided by ZIMRA |
| Device ID | `41872` | Provided by ZIMRA |
| Device model name | `FiscGuy-v1` | Your device model |
| Device model version | `1.0.0` | Your device version |
| Device serial number | `SN0001` | Your device serial |
| Production? | `y/n` | Use production or test FDMS |

The command then:
1. Creates the `Device` record in your database
2. Generates an RSA key pair and CSR
3. Registers the device with ZIMRA FDMS
4. Obtains a signed certificate and stores it in `Certs`
5. Fetches and persists taxpayer configuration and taxes

---

## Verify Setup

```python
from fiscguy.models import Device, Configuration, Taxes

# Device should exist
device = Device.objects.first()
print(device)  # "Cas Bz - 41872"

# Config should be populated
config = Configuration.objects.first()
print(config.tax_payer_name)

# Taxes should be populated
print(Taxes.objects.all())
```

---

## Environment: Test vs Production

`init_device` asks whether to use the production or testing FDMS. This sets `Device.production` and `Certs.production`, which determines which FDMS URL is used:

| Environment | URL |
|-------------|-----|
| Testing | `https://fdmsapitest.zimra.co.zw` |
| Production | `https://fdmsapi.zimra.co.zw` |

To switch environments, re-run `init_device`.

---

## Development Dependencies

```bash
pip install -e ".[dev]"
```

Includes: `pytest`, `pytest-django`, `pytest-cov`, `black`, `isort`, `flake8`, `pylint`, `mypy`, `django-stubs`.

### Pre-commit hooks

```bash
pre-commit install
```

Runs `black`, `isort`, and `flake8` on every commit.

---

## Troubleshooting

### `RuntimeError: No Device found`

Run `python manage.py init_device`.

### Configuration record is missing

If the `Configuration` table is still empty after setup, the initial sync did not complete.
Run `python manage.py init_device` again, or manually refresh configuration:

```python
from fiscguy import get_configuration
get_configuration()
```

### `MalformedFraming: Unable to load PEM file`

The certificate stored in `Certs` is corrupted or missing. Re-run `init_device`.

### `No open fiscal day`

Open a fiscal day before submitting receipts:

```python
from fiscguy import open_day
open_day()
```

### Certificate expired

```bash
# via REST endpoint
POST /fiscguy/issue-certificate/

# or via Python
from fiscguy.services.certs_service import CertificateService
from fiscguy.models import Device
CertificateService(Device.objects.first()).issue_certificate()
```
