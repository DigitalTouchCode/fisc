# FiscGuy

**ZIMRA Fiscal Device Integration Library** — a Django app that handles the full fiscal device lifecycle: device registration, certificate management, fiscal day operations, and receipt submission to ZIMRA FDMS.

[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-4.2%2B-green)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [Requirements](#requirements)
- [Installation](#installation)
- [Django Setup](#django-setup)
- [Device Initialisation](#device-initialisation)
- [API Reference](#api-reference)
  - [Fiscal Day](#fiscal-day)
  - [Receipts](#receipts)
  - [Buyers](#buyers)
  - [Configuration & Taxes](#configuration--taxes)
  - [Device Management](#device-management)
  - [Certificate Management](#certificate-management)
- [Data Models](#data-models)
- [Request & Response Examples](#request--response-examples)
- [Error Handling](#error-handling)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

---

## Overview

FiscGuy plugs into your existing Django project and exposes a REST API that bridges your application to the ZIMRA Fiscal Device Management System (FDMS). It handles:

- **Device registration** — RSA key generation, CSR creation, and ZIMRA certificate issuance
- **Fiscal day management** — open and close fiscal days, tracking counters per day
- **Receipt submission** — create fiscal invoices, credit notes, and debit notes; hash, sign, and submit to FDMS
- **QR code generation** — auto-generated and stored on every submitted receipt
- **Certificate renewal** — re-issue expired certificates without re-registering the device
- **Tax & configuration sync** — pull the latest taxpayer config and applicable taxes from FDMS

FiscGuy exposes a REST API you can call from any HTTP client.

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.11, 3.12, or 3.13 |
| Django | 4.2+ |
| Django REST Framework | 3.14+ |

---

## Installation

### From PyPI

```bash
pip install fiscguy
```

### From Source

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
    # ... your other apps
]
```

### 2. Run Migrations

```bash
python manage.py migrate
```

### 3. Include URLs

```python
# your_project/urls.py
from django.urls import path, include

urlpatterns = [
    path("fiscguy/", include("fiscguy.urls")),
]
```

All FiscGuy endpoints will then be available under `/fiscguy/`.

### 4. Configure Media Files (for QR Codes)

FiscGuy saves receipt QR codes to `MEDIA_ROOT`. Add the following to your settings:

```python
# settings.py
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```

Serve media files in development:

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

Run this **once** per device before using any other feature. This is the most important setup step.

```bash
python manage.py init_device
```

You will be prompted interactively:

| Prompt | Example | Description |
|---|---|---|
| Environment | `yes` / `no` | `yes` for production, `no` for test |
| Organisation name | `org_name` | Your registered company name |
| Device ID | `78412` | Provided by ZIMRA |
| Activation key | `ABC-123-XYZ` | Provided by ZIMRA |
| Device model name | `FiscGuy-v1` | Your device model name |
| Device model version | `1.0.0` | Your device model version |
| Device serial number | `SN0001` | Your device's serial number |

**What happens during init:**

1. Creates the `Device` record in your database
2. Generates an RSA key pair and a Certificate Signing Request (CSR)
3. Registers the device with ZIMRA FDMS (`POST /Public/v1/{device_id}/RegisterDevice`)
4. Stores the signed certificate in the `Certs` model
5. Fetches and persists taxpayer configuration and applicable taxes from FDMS

### Switching Environments (Test ↔ Production)

Re-running `init_device` with a different environment will prompt you to confirm deletion of **all existing data** (receipts, fiscal days, counters, configuration, certificates, taxes) before proceeding. Type `YES` to confirm.

| Environment | FDMS URL |
|---|---|
| Testing | `https://fdmsapitest.zimra.co.zw` |
| Production | `https://fdmsapi.zimra.co.zw` |

---

## API Reference

All endpoints are prefixed with `/fiscguy/` (based on your URL configuration).

---

### Fiscal Day

#### Open Fiscal Day

Opens a new fiscal day for the registered device. If a fiscal day is already open, returns it immediately. On open, taxpayer configuration is also synced from FDMS.

```
POST /fiscguy/open-day/
```

**Request body:** none

**Response `200 OK`:**
```json
{
  "success": true,
  "fiscal_day_no": 42,
  "fdms_response": { ... }
}
```

**Response when already open:**
```json
{
  "success": true,
  "fiscal_day_no": 42,
  "message": "Fiscal day 42 already open"
}
```

---

#### Close Fiscal Day

Closes the currently open fiscal day. Builds fiscal counters, signs the closing payload, and submits to FDMS.

```
POST /fiscguy/close-day/
```

**Request body:** none

**Response `200 OK`:**
```json
{
  "success": true,
  "fiscal_day_no": 42,
  "fdms_response": { ... }
}
```

---

### Receipts

#### List Receipts

Returns all receipts in reverse chronological order with cursor-based pagination. Each receipt includes its full buyer object and all line items.

```
GET /fiscguy/receipts/
```

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `cursor` | string | — | Pagination cursor from a previous response |
| `page_size` | integer | `10` | Number of results per page (max `100`) |

**Response `200 OK`:**
```json
{
  "next": "http://example.com/fiscguy/receipts/?cursor=cD0yMDI...",
  "previous": null,
  "results": [
    {
      "id": 1,
      "device": 1,
      "receipt_number": "R-00000001",
      "receipt_type": "fiscalinvoice",
      "total_amount": "150.00",
      "qr_code": "/media/Zimra_qr_codes/receipt_1.png",
      "code": null,
      "currency": "USD",
      "global_number": 1,
      "hash_value": "abc123...",
      "signature": "def456...",
      "zimra_inv_id": "INV-001",
      "buyer": {
        "id": 1,
        "name": "Casy Holdings",
        "address": "123 Main St, Harare",
        "tin_number": "2000123456",
        "trade_name": "Casy Retail",
        "email": "accounts@casy.co.zw",
        "phonenumber": "+263771234567",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z"
      },
      "payment_terms": "Cash",
      "submitted": true,
      "is_credit_note": false,
      "credit_note_reason": null,
      "credit_note_reference": null,
      "lines": [
        {
          "id": 1,
          "product": "Maize Meal 10kg",
          "quantity": "2.00",
          "unit_price": "50.00",
          "line_total": "100.00",
          "tax_amount": "13.04",
          "tax_type": 1
        },
        {
          "id": 2,
          "product": "Cooking Oil 2L",
          "quantity": "1.00",
          "unit_price": "50.00",
          "line_total": "50.00",
          "tax_amount": "6.52",
          "tax_type": 1
        }
      ],
      "created_at": "2024-01-15T10:05:00Z",
      "updated_at": "2024-01-15T10:05:12Z"
    }
  ]
}
```

---

#### Create & Submit a Receipt

Creates a receipt, signs it cryptographically, generates a QR code, updates fiscal counters, and submits it to ZIMRA FDMS — all in a single atomic operation. If submission fails, the receipt is **not saved** to the database.

```
POST /fiscguy/receipts/
```

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `receipt_type` | string | Yes | `fiscalinvoice`, `creditnote`, or `debitnote` |
| `total_amount` | decimal | Yes | Total amount (must be negative for credit notes) |
| `currency` | string | Yes | `USD` or `ZWG` |
| `payment_terms` | string | Yes | `Cash`, `Card`, `MobileWallet`, `BankTransfer`, `Coupon`, `Credit`, or `Other` |
| `lines` | array | Yes | One or more receipt line items (see below) |
| `buyer` | object | No | Full buyer object (see below). Omit for anonymous sales. |
| `credit_note_reference` | string | Required for `creditnote` | The `receipt_number` of the original receipt being credited |
| `credit_note_reason` | string | No | Human-readable reason for the credit note |

**Receipt line fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `product` | string | Yes | Product or service name |
| `quantity` | decimal | Yes | Quantity sold |
| `unit_price` | decimal | Yes | Price per unit |
| `line_total` | decimal | Yes | Total for this line (`quantity × unit_price`) |
| `tax_amount` | decimal | Yes | Tax amount for this line |
| `tax_name` | string | No | Tax name as configured in ZIMRA (e.g. `"Standard rated 15.5"`). Used to link the line to a `Taxes` record. |

**Buyer fields (full object, not an ID):**

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Registered business name |
| `tin_number` | string | Yes | 10-digit ZIMRA TIN number |
| `address` | string | No | Physical address |
| `trade_name` | string | No | Trading name / branch name |
| `email` | string | No | Contact email |
| `phonenumber` | string | No | Contact phone number |

> **Note on buyers:** The buyer is looked up by `tin_number`. If a buyer with the given TIN already exists, the existing record is reused. If not, a new `Buyer` is created. You always pass the full buyer object — never a buyer ID.

**Example — Fiscal Invoice with a Buyer:**

```json
{
  "receipt_type": "fiscalinvoice",
  "total_amount": "150.00",
  "currency": "USD",
  "payment_terms": "Cash",
  "buyer": {
    "name": "Casy Holdings",
    "tin_number": "2000123456",
    "address": "123 Main St, Harare",
    "trade_name": "Casy Retail",
    "email": "accounts@casy.co.zw",
    "phonenumber": "+263771234567"
  },
  "lines": [
    {
      "product": "Maize Meal 10kg",
      "quantity": 2,
      "unit_price": "50.00",
      "line_total": "100.00",
      "tax_amount": "13.04",
      "tax_name": "Standard rated 15.5"
    },
    {
      "product": "Cooking Oil 2L",
      "quantity": 1,
      "unit_price": "50.00",
      "line_total": "50.00",
      "tax_amount": "6.52",
      "tax_name": "Standard rated 15.5"
    }
  ]
}
```

**Example — Anonymous Fiscal Invoice (no buyer):**

```json
{
  "receipt_type": "fiscalinvoice",
  "total_amount": "25.00",
  "currency": "USD",
  "payment_terms": "Card",
  "lines": [
    {
      "product": "Bread",
      "quantity": 1,
      "unit_price": "25.00",
      "line_total": "25.00",
      "tax_amount": "3.26",
      "tax_name": "Standard rated 15.5"
    }
  ]
}
```

**Example — Credit Note:**

```json
{
  "receipt_type": "creditnote",
  "total_amount": "-150.00",
  "currency": "USD",
  "payment_terms": "Cash",
  "credit_note_reference": "R-00000001",
  "credit_note_reason": "Goods returned by customer",
  "buyer": {
    "name": "Casy Holdings",
    "tin_number": "2000123456",
    "address": "123 Main St, Harare",
    "trade_name": "Casy Retail",
    "email": "accounts@casy.co.zw",
    "phonenumber": "+263771234567"
  },
  "lines": [
    {
      "product": "Maize Meal 10kg",
      "quantity": 2,
      "unit_price": "50.00",
      "line_total": "100.00",
      "tax_amount": "13.04",
      "tax_name": "Standard rated 15.5"
    },
    {
      "product": "Cooking Oil 2L",
      "quantity": 1,
      "unit_price": "50.00",
      "line_total": "50.00",
      "tax_amount": "6.52",
      "tax_name": "Standard rated 15.5"
    }
  ]
}
```

**Response `201 Created`:**

Returns the full receipt object (same shape as the list endpoint) including `receipt_number`, `global_number`, `hash_value`, `signature`, `zimra_inv_id`, and `qr_code`.

**Response `422 Unprocessable Entity`** (ZIMRA rejected the receipt):
```json
{
  "error": "FDMS returned an error: ..."
}
```

---

### Buyers

Buyers are automatically created or retrieved when submitting a receipt (keyed by `tin_number`). The Buyer viewset also provides standalone CRUD endpoints.

#### List Buyers

```
GET /fiscguy/buyer/
```

**Response `200 OK`:**
```json
[
  {
    "id": 1,
    "name": "Casy Holdings",
    "address": "123 Main St, Harare",
    "tin_number": "2000123456",
    "trade_name": "Casy Retail",
    "email": "accounts@casy.co.zw",
    "phonenumber": "+263771234567",
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T10:00:00Z"
  }
]
```

#### Create Buyer

```
POST /fiscguy/buyer/
```

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Registered business name |
| `tin_number` | string | Yes | 10-digit ZIMRA TIN number |
| `address` | string | No | Physical address |
| `trade_name` | string | No | Trading name / branch name |
| `email` | string | No | Contact email |
| `phonenumber` | string | No | Contact phone number |

**Example:**
```json
{
  "name": "Casy Holdings",
  "tin_number": "2000123456",
  "address": "123 Main St, Harare",
  "trade_name": "Casy Retail",
  "email": "accounts@casy.co.zw",
  "phonenumber": "+263771234567"
}
```

**Response `201 Created`:** Returns the created buyer object.

#### Retrieve Buyer

```
GET /fiscguy/buyer/{id}/
```

#### Update Buyer

```
PUT /fiscguy/buyer/{id}/
PATCH /fiscguy/buyer/{id}/
```

#### Delete Buyer

```
DELETE /fiscguy/buyer/{id}/
```

---

### Configuration & Taxes

#### Get Configuration

Returns the stored taxpayer configuration for the registered device.

```
GET /fiscguy/configuration/
```

**Response `200 OK`:**
```json
{
  "id": 1,
  "device": 1,
  "tax_payer_name": "ACME Ltd",
  "tin_number": "1234567890",
  "vat_number": "V123456789",
  "address": "10 Commerce Drive, Harare",
  "phone_number": "+263771234567",
  "email": "tax@acme.co.zw",
  "created_at": "2024-01-01T08:00:00Z",
  "updated_at": "2024-01-15T09:30:00Z"
}
```

Returns `{}` if no device or configuration is found.

---

#### Sync Configuration

Manually pulls the latest configuration from ZIMRA FDMS and updates the local database. This is also called automatically when opening a fiscal day.

```
POST /fiscguy/sync-config/
```

**Request body:** none

**Response `200 OK`:**
```json
{
  "message": "Configuration Synced"
}
```

---

#### List Taxes

Returns all tax types currently configured in ZIMRA for this device.

```
GET /fiscguy/taxes/
```

**Response `200 OK`:**
```json
[
  {
    "id": 1,
    "code": "A",
    "name": "Standard rated 15.5",
    "tax_id": 1,
    "percent": "15.00",
    "created_at": "2024-01-01T08:00:00Z"
  },
  {
    "id": 2,
    "code": "B",
    "name": "Zero Rat rated 15.5ed",
    "tax_id": 2,
    "percent": "0.00",
    "created_at": "2024-01-01T08:00:00Z"
  },
  {
    "id": 3,
    "code": "C",
    "name": "Exempt",
    "tax_id": 3,
    "percent": "0.00",
    "created_at": "2024-01-01T08:00:00Z"
  }
]
```

---

### Device Management

#### Get Device Status

Fetches the current device and fiscal day status directly from ZIMRA FDMS.

```
GET /fiscguy/get-status/
```

**Response `200 OK`:**
```json
{
  "lastFiscalDayNo": 41,
  "lastReceiptGlobalNo": 150,
  "fiscalDayStatus": "Closed",
  ...
}
```

---

#### Ping Device

Reports device connectivity to ZIMRA FDMS. Use this to confirm the device is online and communicating correctly.

```
POST /fiscguy/get-ping/
```

**Request body:** none

**Response `200 OK`:**
```json
{
  "success": true,
  ...
}
```

---

### Certificate Management

#### Issue / Renew Certificate

Renews the device certificate with ZIMRA FDMS. Use this when the current certificate has expired.

```
POST /fiscguy/issue-certificate/
```

**Request body:** none

**Response `200 OK`:**
```json
{
  "message": "Certificate issued successfully"
}
```

**Response `422 Unprocessable Entity`** (renewal failed):
```json
{
  "error": "Certificate renewal issuance failed."
}
```

---

## Data Models

### Device

Represents a registered ZIMRA fiscal device.

| Field | Type | Description |
|---|---|---|
| `org_name` | CharField | Organisation name |
| `activation_key` | CharField | ZIMRA activation key |
| `device_id` | CharField (unique) | ZIMRA device identifier |
| `device_model_name` | CharField | Device model name |
| `device_serial_number` | CharField | Device serial number |
| `device_model_version` | CharField | Device model version |
| `production` | BooleanField | `True` = production, `False` = test |
| `created_at` | DateTimeField | Auto-set on creation |

---

### Configuration

Taxpayer configuration synced from ZIMRA FDMS. One-to-one with `Device`.

| Field | Type | Description |
|---|---|---|
| `device` | OneToOne → Device | Linked device |
| `tax_payer_name` | CharField | Registered taxpayer name |
| `tax_inclusive` | BooleanField | Whether prices include tax |
| `tin_number` | CharField | 10-digit TIN |
| `vat_number` | CharField | registra rated 15.5tion number |
| `address` | CharField | Business address |
| `phone_number` | CharField | Contact phone |
| `email` | EmailField | Contact email |
| `url` | URLField | FDMS URL (test or production) |

---

### Certs

TLS client certificate for FDMS communication. One-to-one with `Device`.

| Field | Type | Description |
|---|---|---|
| `device` | OneToOne → Device | Linked device |
| `csr` | TextField | PEM-encoded Certificate Signing Request |
| `certificate` | TextField | PEM-encoded signed certificate |
| `certificate_key` | TextField | PEM-encoded private key |
| `production` | BooleanField | `True` = production certificate |

---

### FiscalDay

A fiscal day record. Increments by 1 each time a day is opened.

| Field | Type | Description |
|---|---|---|
| `device` | FK → Device | Linked device |
| `day_no` | IntegerField | Sequential fiscal day number |
| `receipt_counter` | IntegerField | Number of receipts in this day |
| `is_open` | BooleanField | Whether this day is currently open |

---

### FiscalCounter

Running totals for each tax type and money type within a fiscal day. Updated on every receipt submission.

| Field | Type | Description |
|---|---|---|
| `device` | FK → Device | Linked device |
| `fiscal_day` | FK → FiscalDay | Linked fiscal day |
| `fiscal_counter_type` | CharField | `SaleByTax`, `SaleTaxByTax`, `CreditNoteByTax`, `CreditNoteTaxByTax`, `DebitNoteByTax`, `DebitNoteTaxByTax`, `BalanceByMoneyType`, `Other` |
| `fiscal_counter_currency` | CharField | `USD` or `ZWG` |
| `fiscal_counter_tax_percent` | DecimalField | Tax rate for this counter |
| `fiscal_counter_tax_id` | IntegerField | ZIMRA tax ID for this counter |
| `fiscal_counter_money_type` | CharField | `Cash`, `Card`, `BankTransfer`, `MobileMoney` |
| `fiscal_counter_value` | DecimalField | Running total value |

---

### Taxes

Tax types applicable to this device, synced from ZIMRA.

| Field | Type | Description |
|---|---|---|
| `code` | CharField | Short code (e.g. `A`, `B`, `C`) |
| `name` | CharField | Full name (e.g. `Standard rated 15.5`) |
| `tax_id` | IntegerField | ZIMRA internal tax ID |
| `percent` | DecimalField | Tax percentage |

---

### Receipt

A submitted fiscal receipt.

| Field | Type | Description |
|---|---|---|
| `device` | FK → Device | Device that issued this receipt |
| `receipt_number` | CharField (unique) | Auto-generated, format `R-{global_number:08d}` |
| `receipt_type` | CharField | `fiscalinvoice`, `creditnote`, or `debitnote` |
| `total_amount` | DecimalField | Receipt total (negative for credit notes) |
| `qr_code` | ImageField | Path to stored QR code image |
| `currency` | CharField | `USD` or `ZWG` |
| `global_number` | IntegerField | FDMS global receipt sequence number |
| `hash_value` | CharField | SHA-256 hash of the receipt string |
| `signature` | TextField | RSA signature |
| `zimra_inv_id` | CharField | ZIMRA invoice ID from FDMS response |
| `buyer` | FK → Buyer (nullable) | Linked buyer, or null for anonymous sales |
| `payment_terms` | CharField | Payment method |
| `submitted` | BooleanField | Whether successfully submitted to FDMS |
| `is_credit_note` | BooleanField | Auto-set for credit note receipt types |
| `credit_note_reason` | CharField | Reason for credit note |
| `credit_note_reference` | CharField | `receipt_number` of the original receipt |

---

### ReceiptLine

A single line item on a receipt.

| Field | Type | Description |
|---|---|---|
| `receipt` | FK → Receipt | Parent receipt |
| `product` | CharField | Product or service name |
| `quantity` | DecimalField | Quantity |
| `unit_price` | DecimalField | Price per unit |
| `line_total` | DecimalField | `quantity × unit_price` |
| `tax_amount` | DecimalField | Tax amount for this line |
| `tax_type` | FK → Taxes (nullable) | Linked tax record |

---

### Buyer

A register rated 15.5ed buyer. Keyed by `tin_number` — reused across receipts when the TIN matches.

| Field | Type | Description |
|---|---|---|
| `name` | CharField | Registered business name |
| `address` | CharField | Physical address |
| `phonenumber` | CharField | Contact phone |
| `trade_name` | CharField | Trading / branch name |
| `tin_number` | CharField | 10-digit ZIMRA TIN |
| `email` | EmailField | Contact email |

---

## Error Handling

FiscGuy uses a structured exception hierarchy. All exceptions inherit from `FiscalisationError`.

| Exception | When raised |
|---|---|
| `FiscalisationError` | Base class for all fiscalisation errors |
| `CertNotFoundError` | No certificate found in the database |
| `CryptoError` | Cryptographic operation failed |
| `PersistenceError` | Database write failed |
| `RegistrationError` | General device registration failure |
| `DeviceNotFoundError` | No device registered |
| `ZIMRAAPIError` | ZIMRA API returned an error |
| `ValidationError` | Input data failed validation |
| `AuthenticationError` | Authentication failed |
| `ConfigurationError` | Configuration missing or invalid |
| `TaxError` | Tax-related operation failed |
| `FiscalDayError` | Opening a fiscal day failed |
| `ReceiptSubmissionError` | Receipt processing or submission failed |
| `DeviceRegistrationError` | Device registration failed |
| `CertificateError` | Certificate issue or renewal failed |
| `StatusError` | FDMS status check failed |
| `DevicePingError` | Device ping failed |
| `CloseDayError` | Closing a fiscal day failed |

### HTTP Status Codes

| Status | Meaning |
|---|---|
| `200 OK` | Request succeeded |
| `201 Created` | Receipt created and submitted |
| `400 Bad Request` | Invalid input (fiscal day already open, etc.) |
| `404 Not Found` | No device registered |
| `422 Unprocessable Entity` | ZIMRA rejected the receipt / certificate / close day |
| `500 Internal Server Error` | Unexpected server error |

---

## Development

### Install Development Dependencies

```bash
pip install -e ".[dev]"
```

Includes: `pytest`, `pytest-django`, `pytest-cov`, `black`, `isort`, `flake8`, `pylint`, `mypy`, `django-stubs`.

### Run Tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=fiscguy --cov-report=term-missing
```

### Code Style

```bash
# Format
black fiscguy/

# Sort imports
isort fiscguy/

# Lint
flake8 fiscguy/
```

### Pre-commit Hooks

```bash
pre-commit install
```

Runs `black`, `isort`, and `flake8` on every commit.

---

## Troubleshooting

### `RuntimeError: No Device found`

No device has been registered yet. Run:

```bash
python manage.py init_device
```

---

### `RuntimeError: ZIMRA configuration missing`

The `Configuration` record is missing. Either `init_device` didn't complete successfully. Sync manually via the REST API:

```
POST /fiscguy/sync-config/
```

---

### `MalformedFraming: Unable to load PEM file`

The certificate stored in `Certs` is corrupted or empty. Re-run device registration:

```bash
python manage.py init_device
```

---

### `No open fiscal day`

You must open a fiscal day before submitting receipts:

```
POST /fiscguy/open-day/
```

---

### Certificate Expired

Renew the certificate without re-registering the device:

```
POST /fiscguy/issue-certificate/
```

---

### Receipt Submission Fails (`422`)

- Verify a fiscal day is open (`GET /fiscguy/get-status/`)
- Verify `total_amount` is negative for credit notes
- Verify `credit_note_reference` matches an existing `receipt_number` for credit notes
- Verify `tin_number` is exactly 10 digits
- Check ZIMRA FDMS connectivity via `POST /fiscguy/get-ping/`

---

## License

MIT — see [LICENSE](LICENSE) for details.

Developed by [Casper Moyo](mailto:cassymyo@gmail.com).
