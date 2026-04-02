# FiscGuy Architecture & Engineering Documentation

This document provides comprehensive technical documentation for FiscGuy developers and maintainers.

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Data Models](#data-models)
4. [Service Layer](#service-layer)
5. [Cryptography & Security](#cryptography--security)
6. [ZIMRA Integration](#zimra-integration)
7. [Receipt Processing Pipeline](#receipt-processing-pipeline)
8. [Fiscal Day Management](#fiscal-day-management)
9. [Error Handling](#error-handling)
10. [Database Design](#database-design)
11. [Development Guidelines](#development-guidelines)

## Project Overview

FiscGuy is a Django-based library for integrating with ZIMRA (Zimbabwe Revenue Authority) fiscal devices. It manages:

- **Device Registration & Management** - Certificate-based authentication with ZIMRA FDMS
- **Receipt Generation & Submission** - Full receipt lifecycle with cryptographic signing
- **Fiscal Day Operations** - Opening/closing fiscal days with counter management
- **Configuration Management** - Device and taxpayer configuration persistence
- **Tax Management** - Support for multiple tax types and rates

**Technology Stack:**
- Django 4.2+
- Django REST Framework
- Cryptography (RSA, SHA-256, MD5)
- QRCode Generation
- ZIMRA FDMS API (HTTPS with certificate-based auth)

## Architecture

FiscGuy follows a **layered architecture**:

```
┌─────────────────────────────────────────────────────┐
│              REST API Layer (views.py)               │
│  ReceiptView, OpenDayView, CloseDayView, etc.       │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────┴──────────────────────────────────┐
│           Service Layer (services/)                  │
│  ReceiptService, OpenDayService, ClosingDayService  │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────┴──────────────────────────────────┐
│      Data Persistence Layer (models.py)              │
│  Device, Receipt, FiscalDay, Configuration, etc.    │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────┴──────────────────────────────────┐
│    ZIMRA Integration Layer (zimra_*.py)             │
│  ZIMRAClient, ZIMRACrypto, ZIMRAReceiptHandler      │
└──────────────────┬──────────────────────────────────┘
                   │
                   ↓
         ZIMRA FDMS REST API
```

### Layer Responsibilities

#### 1. REST API Layer (`views.py`)
- **ReceiptView** - List/paginate receipts (GET), create & submit receipts (POST)
- **OpenDayView** - Open fiscal day operations
- **CloseDayView** - Close fiscal day and calculate counters
- **StatusView** - Query device status from ZIMRA
- **ConfigurationView** - Fetch device configuration
- **TaxView** - List available taxes
- **BuyerViewset** - CRUD operations for buyers

#### 2. Service Layer (`services/`)

**ReceiptService** - Orchestrates receipt creation and submission:
- Validates receipt payload via serializers
- Persists receipt to database
- Delegates processing to ZIMRAReceiptHandler
- Returns atomic operation result (all-or-nothing)

**OpenDayService** - Opens fiscal day on ZIMRA:
- Queries ZIMRA for next day number
- Creates FiscalDay record
- Auto-called if no open day exists when submitting receipt

**ClosingDayService** - Closes fiscal day:
- Queries ZIMRA for fiscal counters
- Builds counters hashstring per spec
- Sends closing request to ZIMRA
- Updates local FiscalDay record

**ConfigurationService** - Synchronizes configuration:
- Fetches device config from ZIMRA
- Syncs taxes from ZIMRA
- Manages tax updates

**StatusService** - Queries ZIMRA status
**PingService** - Device connectivity check
**CertsService** - Certificate management

#### 3. Data Persistence Layer (`models.py`)

See [Data Models](#data-models) section below.

#### 4. ZIMRA Integration Layer

**ZIMRAClient** (`zimra_base.py`):
- HTTP/HTTPS requests to ZIMRA FDMS
- Certificate-based authentication
- Request/response handling
- Timeout management (30s default)

**ZIMRACrypto** (`zimra_crypto.py`):
- RSA signing with SHA-256
- SHA-256 hashing for integrity
- MD5 for verification code generation
- QR code verification code from signature

**ZIMRAReceiptHandler** (`zimra_receipt_handler.py`):
- Complete receipt processing pipeline
- Receipt data building per ZIMRA spec
- Hash and signature generation
- QR code creation
- Fiscal counter updates
- FDMS submission

## Data Models

### Device
```python
Fields:
- org_name: str (max 255)
- activation_key: str (max 255)
- device_id: str (unique, max 100)
- device_model_name: str (optional)
- device_serial_number: str (optional)
- device_model_version: str (optional)
- production: bool (test/production environment flag)
- created_at: datetime (auto_now_add)

Relationships:
- configuration (OneToOne) → Configuration
- certificate (OneToOne) → Certs
- fiscal_days (OneToMany) → FiscalDay
- fiscal_counters (OneToMany) → FiscalCounter
- receipts (OneToMany) → Receipt
```

**Purpose:** Represents a physical/logical ZIMRA fiscal device. Multiple devices can be registered (e.g., different POS terminals).

### Configuration
```python
Fields:
- device: OneToOneField → Device
- tax_payer_name: str (max 255)
- tin_number: str (max 20)
- vat_number: str (max 20)
- address: str (max 255)
- phone_number: str (max 20)
- email: EmailField
- url: URLField (test/production ZIMRA endpoint)
- tax_inclusive: bool (tax calculation mode)
- created_at/updated_at: datetime

Relationships:
- device (OneToOne) → Device
```

**Purpose:** Stores taxpayer configuration synced from ZIMRA. One config per device.

### Certs
```python
Fields:
- device: OneToOneField → Device
- csr: TextField (Certificate Signing Request)
- certificate: TextField (X.509 certificate)
- certificate_key: TextField (RSA private key)
- production: bool (test/production cert)
- created_at/updated_at: datetime

Relationships:
- device (OneToOne) → Device
```

**Purpose:** Stores device certificates and private keys for ZIMRA authentication.

### FiscalDay
```python
Fields:
- device: ForeignKey → Device
- day_no: int (ZIMRA fiscal day number)
- receipt_counter: int (receipts issued today, default 0)
- is_open: bool (day open/closed)
- created_at/updated_at: datetime

Constraints:
- unique_together: (device, day_no)

Indexes:
- (device, is_open) - for fast open day queries
```

**Purpose:** Represents a fiscal day (accounting period). Each device has one open fiscal day at a time.

### FiscalCounter
```python
Fields:
- device: ForeignKey → Device
- fiscal_day: ForeignKey → FiscalDay
- fiscal_counter_type: CharField
  - SaleByTax, SaleTaxByTax
  - CreditNoteByTax, CreditNoteTaxByTax
  - DebitNoteByTax, DebitNoteTaxByTax
  - BalanceByMoneyType, Other
- fiscal_counter_currency: CharField (USD, ZWG)
- fiscal_counter_tax_percent: Decimal (optional)
- fiscal_counter_tax_id: int (optional)
- fiscal_counter_money_type: CharField (Cash, Card, BankTransfer, MobileMoney)
- fiscal_counter_value: Decimal (accumulated counter value)
- created_at/updated_at: datetime

Constraints:
- Indexed: (device, fiscal_day)

Relationships:
- device (ForeignKey) → Device
- fiscal_day (ForeignKey) → FiscalDay
```

**Purpose:** Accumulates receipt values by type, currency, and tax. Updated on receipt submission. Used to close fiscal day.

### Receipt
```python
Fields:
- device: ForeignKey → Device (FIXED: was missing, added in v0.1.6)
- receipt_number: str (unique, auto-generated as R-{global_number:08d})
- receipt_type: str
  - fiscalinvoice (normal receipt)
  - creditnote (debit customer)
  - debitnote (credit customer, not mandatory)
- total_amount: Decimal (12 digits, 2 decimals)
- currency: str (USD or ZWG)
- qr_code: ImageField (PNG, uploaded to Zimra_qr_codes/)
- code: str (verification code, extracted from signature)
- global_number: int (ZIMRA global receipt number)
- hash_value: str (SHA-256 hash)
- signature: TextField (RSA signature, base64)
- zimra_inv_id: str (ZIMRA internal receipt ID)
- buyer: ForeignKey → Buyer (optional)
- payment_terms: str (Cash, Card, BankTransfer, MobileWallet, Coupon, Credit, Other)
- submitted: bool (whether sent to ZIMRA)
- is_credit_note: bool
- credit_note_reason: str (optional)
- credit_note_reference: str (receipt_number of original receipt)
- created_at/updated_at: datetime

Constraints:
- receipt_number: unique

Relationships:
- device (ForeignKey) → Device
- buyer (ForeignKey) → Buyer (optional)
- lines (OneToMany) → ReceiptLine
```

**Purpose:** Core receipt entity. Stores receipt data, cryptographic material, and ZIMRA metadata.

### ReceiptLine
```python
Fields:
- receipt: ForeignKey → Receipt
- product: str (max 255)
- quantity: Decimal (10 digits, 2 decimals)
- unit_price: Decimal (12 digits, 2 decimals)
- line_total: Decimal (quantity × unit_price, 12 digits, 2 decimals)
- tax_amount: Decimal (12 digits, 2 decimals)
- tax_type: ForeignKey → Taxes (optional)
- created_at/updated_at: datetime

Constraints:
- Indexed: (receipt)

Relationships:
- receipt (ForeignKey) → Receipt
- tax_type (ForeignKey) → Taxes (optional)
```

**Purpose:** Line items on a receipt (products/services).

### Taxes
```python
Fields:
- code: str (tax code, max 10)
- name: str (human-readable tax name, max 100)
- tax_id: int (ZIMRA tax identifier)
- percent: Decimal (tax rate, 5 digits, 2 decimals)
- created_at: datetime

Constraints:
- Indexed: (tax_id)
- Ordered by: tax_id

Example rows:
- Standard Rated 15.5%, tax_id=1, percent=15.50
- Zero Rated 0%, tax_id=4, percent=0.00
- Exempt 0%, tax_id=5, percent=0.00
```

**Purpose:** Tax type definitions. Auto-synced from ZIMRA on configuration init and day opening.

### Buyer
```python
Fields:
- name: str (max 255, registered business name)
- address: str (max 255, optional)
- tin_number: str (max 255, unique within buyer records)
- trade_name: str (max 100, optional, e.g., branch name)
- email: EmailField (optional)
- phonenumber: str (max 20, optional)
- created_at/updated_at: datetime

Constraints:
- Indexed: (tin_number)

Relationships:
- receipts (OneToMany) → Receipt
```

**Purpose:** Customer/buyer information. Optional on receipts (can be null for cash sales). Uses `get_or_create` to avoid duplicates by TIN.

## Service Layer

### ReceiptService

**Location:** `fiscguy/services/receipt_service.py`

**Purpose:** Validates, persists, and submits receipts to ZIMRA.

**Key Method:** `create_and_submit_receipt(data: dict) → tuple[Receipt, dict]`

```python
Flow:
1. Adds device ID to request data
2. Validates via ReceiptCreateSerializer
3. Persists receipt to DB (with buyer creation/linking)
4. Fetches fully hydrated receipt (with lines, buyer)
5. Delegates to ZIMRAReceiptHandler.process_and_submit()
6. Returns (Receipt, submission_result)

Atomicity:
- Wrapped in @transaction.atomic
- If submission fails: entire operation rolled back, receipt NOT saved
- If submission succeeds: receipt marked as submitted=True

Raises:
- serializer.ValidationError: invalid payload
- ReceiptSubmissionError: processing/FDMS submission failed
```

### OpenDayService

**Location:** `fiscguy/services/open_day_service.py`

**Purpose:** Opens a new fiscal day with ZIMRA and syncs taxes.

**Key Method:** `open_day() → dict`

```python
Flow:
1. Queries ZIMRA status for next day_no (lastFiscalDayNo + 1)
2. Syncs latest taxes from ZIMRA
3. Creates FiscalDay record (is_open=True)
4. Returns ZIMRA response

Auto-call:
- Triggered automatically if no open day exists when submitting first receipt
- Adds 5-second delay to allow ZIMRA processing
```

### ClosingDayService

**Location:** `fiscguy/services/closing_day_service.py`

**Purpose:** Closes fiscal day and sends closing hash to ZIMRA.

**Key Method:** `close_day() → dict`

```python
Flow:
1. Fetches open FiscalDay
2. Queries ZIMRA for fiscal counters (SaleByTax, SaleTaxByTax, etc.)
3. Fetches local receipts for the day
4. Builds counters per ZIMRA spec (see below)
5. Creates closing hashstring with counters
6. Signs hashstring with RSA
7. Sends closing request to ZIMRA
8. Marks FiscalDay as is_open=False
9. Saves fiscal counters to DB

Counter Ordering (per spec 13.3.1):
- Sorted by (currency ASC, taxID ASC)
- Zero-value counters EXCLUDED
- Format: "counter1|counter2|..."
```

### ConfigurationService

**Location:** `fiscguy/services/configuration_service.py`

**Purpose:** Syncs taxpayer config and taxes from ZIMRA.

**Key Methods:**
- `get_configuration()` - Fetches config from ZIMRA
- `sync_taxes()` - Fetches and updates tax records
- `sync_all()` - Full sync

### StatusService & PingService

- **StatusService** - Queries device status from ZIMRA
- **PingService** - Tests device connectivity

## Cryptography & Security

### ZIMRACrypto

**Location:** `fiscguy/zimra_crypto.py`

**Algorithms:**
- **Signing:** RSA-2048 with PKCS#1 v1.5 padding, SHA-256
- **Hashing:** SHA-256
- **Verification Code:** MD5 (from signature bytes)
- **Encoding:** Base64

**Key Methods:**

#### `generate_receipt_hash_and_signature(signature_string: str) → dict`
```python
signature_string = "receipt|data|string|built|per|spec"
hash_value = SHA256(signature_string)  # base64 encoded
signature = RSA_SIGN(signature_string)  # base64 encoded

Returns: {"hash": hash_value, "signature": signature}
```

**Critical:** The signature_string format is specified by ZIMRA spec (see `ZIMRAReceiptHandler._build_receipt_data()`).

#### `sign_data(data: str) → str`
- Signs arbitrary data with RSA private key
- Returns base64-encoded signature

#### `get_hash(data: str) → str`
- SHA-256 hash, base64-encoded

#### `generate_verification_code(base64_signature: str) → str`
- Extracts 16-character code from signature for QR
- Used in QR code data

#### `load_private_key() → RSAPrivateKey`
- Loads from stored certificate PEM
- Caches result

### Certificate Management

**Location:** `fiscguy/utils/cert_temp_manager.py`

**Purpose:** Manages temporary PEM files for ZIMRA HTTPS authentication.

**Usage:**
- ZIMRAClient creates temporary PEM file from certificate + key
- Session uses cert for mutual TLS authentication
- Cleanup on object destruction

## ZIMRA Integration

### ZIMRAClient

**Location:** `fiscguy/zimra_base.py`

**Purpose:** HTTP client for ZIMRA FDMS API.

**Endpoints:**
- **Device API** (requires cert): `https://fdmsapi[test].zimra.co.zw/Device/v1/{device_id}/...`
- **Public API** (no cert): `https://fdmsapi[test].zimra.co.zw/Public/v1/{device_id}/...`

**Environment Detection:**
- If `Certs.production=True`: uses production URL
- Else: uses test URL

**Key Methods:**
- `register_device(payload)` - Register device (public endpoint, no cert)
- `get_status()` - Query device status (device endpoint)
- `submit_receipt(payload)` - Submit receipt to ZIMRA
- `open_fiscal_day(payload)` - Open fiscal day
- `close_fiscal_day(payload)` - Close fiscal day

**Session Management:**
- Persistent `requests.Session` with cert authentication
- Headers include device model name/version
- Timeout: 30 seconds

### ZIMRA API Payloads

#### Receipt Submission

```json
{
  "receiptNumber": "R-00000001",
  "receiptType": "F",  // F=invoice, C=credit note, D=debit note
  "receiptTotal": 100.00,
  "receiptCurrency": "USD",
  "receiptGlobalNo": 1,
  "receiptDateTime": "2026-04-01T10:30:00Z",
  "receiptDescription": "...",
  "buyerTIN": "1234567890",  // optional
  "paymentMethod": "Cash",
  "receiptLineItems": [
    {
      "itemNumber": 1,
      "itemDescription": "Product",
      "itemQuantity": 1.00,
      "itemUnitPrice": 100.00,
      "itemTaxType": "Standard Rated",
      "itemTaxAmount": 15.50
    }
  ],
  "hash": "base64-encoded-sha256",
  "signature": "base64-encoded-rsa-signature"
}
```

#### Fiscal Day Close

```json
{
  "hash": "base64-encoded-hashstring",
  "signature": "base64-encoded-rsa-signature",
  "counters": [
    {
      "counterType": "SaleByTax",
      "counterCurrency": "USD",
      "counterTaxType": "Standard Rated",
      "counterTaxId": 1,
      "counterValue": 1000.00
    },
    ...
  ]
}
```

## Receipt Processing Pipeline

### Complete Flow

```
POST /api/receipts/
    ↓
ReceiptView.post()
    ↓
ReceiptService.create_and_submit_receipt()
    ├─ ReceiptCreateSerializer.validate()
    │   ├─ Validate credit note (if applicable)
    │   └─ Validate TIN (if buyer provided)
    ├─ ReceiptCreateSerializer.create()
    │   ├─ Get or create Buyer (from buyer_data)
    │   ├─ Create Receipt (device + lines)
    │   └─ Create ReceiptLine items
    │
    ├─ ZIMRAReceiptHandler.process_and_submit()
    │   ├─ _ensure_fiscal_day_open()
    │   │   ├─ Check if FiscalDay open
    │   │   └─ If not: auto-call OpenDayService.open_day()
    │   │
    │   ├─ _build_receipt_data()
    │   │   └─ Construct signature_string per ZIMRA spec
    │   │
    │   ├─ ZIMRACrypto.generate_receipt_hash_and_signature()
    │   │   ├─ SHA256 hash
    │   │   └─ RSA sign
    │   │
    │   ├─ _generate_qr_code()
    │   │   ├─ Extract verification code from signature
    │   │   ├─ Create QR PNG image
    │   │   └─ Save to Receipt.qr_code
    │   │
    │   ├─ _update_fiscal_counters()
    │   │   └─ Increment FiscalCounter values
    │   │
    │   └─ _submit_to_fdms()
    │       ├─ POST receipt to ZIMRA
    │       ├─ Parse response
    │       └─ Return submission_result
    │
    └─ Update Receipt (hash, signature, global_no, zimra_inv_id, submitted=True)
        └─ Save to DB

Returns: Response(ReceiptSerializer(receipt), 201)
```

### Atomic Transaction

The entire flow (ReceiptService.create_and_submit_receipt) is wrapped in `@transaction.atomic`:

```python
@transaction.atomic
def create_and_submit_receipt(self, data: dict):
    # All or nothing
    # If step N fails → all changes rolled back
```

### Automatic Fiscal Day Opening

If no open fiscal day exists:
1. OpenDayService auto-opens one
2. 5-second delay for ZIMRA processing
3. Continues with receipt submission

## Fiscal Day Management

### Fiscal Day Lifecycle

```
State: is_open=False
  ↓ [POST /open-day/]
State: is_open=True, receipts can be submitted
  ↓ [receipts submitted, counters accumulated]
  ↓ [POST /close-day/]
State: is_open=False, counters reset
```

### Fiscal Counter Update

On receipt submission:

```python
for each line_item in receipt.lines:
    for each tax_type on line:
        counter_type = f"SaleByTax" or "SaleTaxByTax" or "CreditNoteByTax" etc.
        counter = FiscalCounter.objects.filter(
            fiscal_day=fiscal_day,
            fiscal_counter_type=counter_type,
            fiscal_counter_currency=receipt.currency,
            fiscal_counter_tax_id=line.tax_type.tax_id
        )
        counter.fiscal_counter_value += line.amount_with_tax
        counter.save()
```

**Raw-level DB Lock:**
To prevent race conditions, counter updates use F() for row-level locking:

```python
FiscalCounter.objects.filter(...).update(
    fiscal_counter_value=F('fiscal_counter_value') + amount
)
```

## Error Handling

### Exception Hierarchy

```
FiscalisationError (base)
├── CertNotFoundError
├── CryptoError
├── DeviceNotFoundError
├── ConfigurationError
├── TaxError
├── FiscalDayError
├── ReceiptSubmissionError
├── StatusError
├── ZIMRAAPIError
├── DeviceRegistrationError
└── ... others
```

### Receipt Submission Error Handling

**Flow:**

```python
try:
    receipt, submission_res = ReceiptService(device).create_and_submit_receipt(data)
    return Response(serializer.data, 201)
except ReceiptSubmissionError as exc:
    # Entire transaction rolled back
    return Response({"error": str(exc)}, 422)
except Exception:
    return Response({"error": "Unexpected error"}, 500)
```

**Key:** If ReceiptSubmissionError is raised, @transaction.atomic ensures the receipt is NOT saved.

### Validation Errors

**ReceiptCreateSerializer.validate():**
- Credit note validation
- TIN validation (10 digits)
- Receipt reference validation
- Amount sign validation (credit notes must be negative)

## Database Design

### Indexes

```python
Device:
  - device_id (UNIQUE)

FiscalDay:
  - (device, day_no) UNIQUE
  - (device, is_open)

FiscalCounter:
  - (device, fiscal_day)

Receipt:
  - receipt_number (UNIQUE)
  - (device, -created_at)

ReceiptLine:
  - (receipt)

Taxes:
  - tax_id

Buyer:
  - tin_number
```

### Relationships

```
Device (1)
  ├─ Configuration (0..1)
  ├─ Certs (0..1)
  ├─ FiscalDay (0..*)
  ├─ FiscalCounter (0..*)
  └─ Receipt (0..*)
       └─ ReceiptLine (1..*)
            └─ Taxes (0..1)
       └─ Buyer (0..1)
```

## Development Guidelines

### Adding New Features

1. **Model Changes**
   - Update `models.py`
   - Create migration: `python manage.py makemigrations fiscguy`
   - Document in ARCHITECTURE.md

2. **API Endpoints**
   - Create view in `views.py`
   - Add to `urls.py`
   - Create serializer in `serializers.py`
   - Add tests in `tests/`

3. **Business Logic**
   - Implement in `services/`
   - Keep views thin (just HTTP handling)
   - Use serializers for validation

4. **ZIMRA Integration**
   - Extend `ZIMRAClient` for new endpoints
   - Handle API responses in services
   - Add error handling

### Testing

**Run all tests:**
```bash
pytest
```

**Coverage:**
```bash
pytest --cov=fiscguy
```

**Specific test:**
```bash
pytest fiscguy/tests/test_receipt_service.py
```

### Code Quality

**Linting:**
```bash
flake8 fiscguy/
```

**Type checking:**
```bash
mypy fiscguy/
```

**Code formatting:**
```bash
black fiscguy/
```

### Atomic Transactions

**Always wrap** state-changing operations (receipt creation, day opening/closing) in `@transaction.atomic`:

```python
@transaction.atomic
def my_state_changing_operation(self):
    # All-or-nothing
    pass
```

### Logging

Use `loguru` for structured logging:

```python
from loguru import logger

logger.info(f"Receipt {receipt.id} submitted")
logger.warning(f"FDMS offline, using provisional number")
logger.error(f"Failed to sign receipt: {e}")
logger.exception(f"Unexpected error")  # includes traceback
```

### Private Methods

Prefix with `_` (e.g., `_build_receipt_data()`, `_ensure_fiscal_day_open()`). Public methods (called from views/tests) have no prefix.

### Model Meta Options

- Always define `ordering` (for consistent query results)
- Use `indexes` for frequently-filtered fields
- Use `unique_together` for composite unique constraints
- Document in docstring

### Serializer Best Practices

- Separate read and write serializers (ReceiptSerializer vs ReceiptCreateSerializer)
- Mark read-only fields: `read_only_fields = [...]`
- Implement `validate()` for cross-field validation
- Use `transaction.atomic` in `create()` for complex nested creates

### Configuration Management

- Store ZIMRA environment URLs in `Configuration.url`
- Certificate environment (test vs production) in `Certs.production`
- Sync config on device init and day opening
- Use `get_or_create` to avoid duplicates

---

**Last Updated:** April 2026  
**Version:** 0.1.6  
**Maintainers:** Casper Moyo (@cassymyo)
