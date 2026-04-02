# FiscGuy — Engineering Architecture

> Internal engineering reference for contributors and maintainers.  
> Version 0.1.6 · Last updated April 2026 · Maintainer: Casper Moyo

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Layer Architecture](#2-layer-architecture)
3. [Component Map](#3-component-map)
4. [Data Models](#4-data-models)
5. [Receipt Processing Pipeline](#5-receipt-processing-pipeline)
6. [Fiscal Day Lifecycle](#6-fiscal-day-lifecycle)
7. [Closing Day & Signature Spec](#7-closing-day--signature-spec)
8. [Cryptography](#8-cryptography)
9. [ZIMRA Client](#9-zimra-client)
10. [Fiscal Counters](#10-fiscal-counters)
11. [Error Handling](#11-error-handling)
12. [Database Design](#12-database-design)
13. [Development Guidelines](#13-development-guidelines)

---

## 1. System Overview

FiscGuy is a Django library that wraps the full ZIMRA Fiscal Device Management System (FDMS) API. It handles every phase of fiscal device integration: device registration, certificate management, fiscal day management, receipt signing and submission, and fiscal counter tracking.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Host Django Application                          │
│                                                                          │
│   from fiscguy import open_day, submit_receipt, close_day               │
│   urlpatterns += [path("fiscguy/", include("fiscguy.urls"))]            │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │       FiscGuy Library    │
                    │                          │
                    │  REST API  →  Services   │
                    │  Services  →  ZIMRA      │
                    │  Services  →  DB         │
                    └────────────┬────────────┘
                                 │  HTTPS + mTLS
                    ┌────────────▼────────────┐
                    │       ZIMRA FDMS         │
                    │                          │
                    │  fdmsapitest.zimra.co.zw │
                    │  fdmsapi.zimra.co.zw     │
                    └──────────────────────────┘
```

---

## 2. Layer Architecture

FiscGuy follows a strict four-layer architecture. Each layer has a single responsibility and communicates only with the layer directly below it.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   REST API LAYER  ·  views.py                                       │
│                                                                     │
│   HTTP in → validate device exists → delegate to service            │
│   Handle typed exceptions → return DRF Response                     │
│   Never contains business logic                                     │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   SERVICE LAYER  ·  services/                                       │
│                                                                     │
│   ReceiptService       OpenDayService       ClosingDayService       │
│   ConfigurationService StatusService        PingService             │
│   CertificateService                                                │
│                                                                     │
│   All business logic lives here. Atomic transactions.               │
│   Raises typed FiscalisationError subclasses on failure.            │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ZIMRA INTEGRATION LAYER  ·  zimra_*.py                            │
│                                                                     │
│   ZIMRAClient           HTTP to FDMS, mTLS, sessions               │
│   ZIMRAReceiptHandler   Full receipt pipeline                       │
│   ZIMRACrypto           RSA signing, SHA-256, MD5, QR               │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   DATA LAYER  ·  models.py                                          │
│                                                                     │
│   Device  Configuration  Certs  FiscalDay  FiscalCounter            │
│   Receipt  ReceiptLine  Taxes  Buyer                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                   SQLite / PostgreSQL / MySQL
```

---

## 3. Component Map

```
fiscguy/
│
├── views.py                   REST endpoints (thin HTTP layer)
├── urls.py                    URL routing
├── models.py                  All Django models
├── serializers.py             DRF serializers (validation + create)
├── exceptions.py              Typed exception hierarchy
├── apps.py                    Django app config
│
├── services/
│   ├── receipt_service.py     Receipt create + submit orchestration
│   ├── open_day_service.py    Fiscal day opening
│   ├── closing_day_service.py Fiscal day closing + counter hash
│   ├── configuration_service.py Tax + config sync from FDMS
│   ├── status_service.py      FDMS status queries
│   ├── ping_service.py        FDMS connectivity check
│   └── certs_service.py       Certificate renewal
│
├── zimra_base.py              ZIMRAClient — HTTP to FDMS
├── zimra_crypto.py            ZIMRACrypto — RSA/SHA256/MD5
├── zimra_receipt_handler.py   ZIMRAReceiptHandler — full pipeline
│
├── utils/
│   ├── cert_temp_manager.py   Temp PEM file lifecycle
│   └── datetime_now.py        Timestamp helpers
│
├── management/
│   └── commands/
│       └── init_device.py     Interactive device registration
│
└── tests/
    ├── conftest.py
    ├── test_views.py
    ├── test_services.py
    ├── test_closing_day_service.py
    └── test_zimra_base.py
```

---

## 4. Data Models

### Entity Relationship

```
                         ┌──────────────┐
                         │    Device    │
                         │──────────────│
                         │ org_name     │
                         │ device_id ◄──┼── unique
                         │ activation_key│
                         │ production   │
                         └──────┬───────┘
                                │
              ┌─────────────────┼──────────────────────┐
              │                 │                       │
    ┌─────────▼──────┐ ┌───────▼──────┐    ┌──────────▼──────┐
    │ Configuration  │ │    Certs     │    │   FiscalDay     │
    │────────────────│ │──────────────│    │─────────────────│
    │ tax_payer_name │ │ csr          │    │ day_no          │
    │ tin_number     │ │ certificate  │    │ receipt_counter │
    │ vat_number     │ │ cert_key     │    │ is_open         │
    │ address        │ │ production   │    └────────┬────────┘
    │ url            │ └──────────────┘             │
    └────────────────┘                    ┌─────────▼──────────┐
                                          │   FiscalCounter    │
              ┌───────────────────────────│────────────────────│
              │                           │ counter_type       │
              │                           │ currency           │
              │                           │ tax_id             │
              │                           │ tax_percent        │
              │                           │ money_type         │
              │                           │ value              │
              │                           └────────────────────┘
    ┌─────────▼──────┐
    │    Receipt     │
    │────────────────│       ┌──────────────┐
    │ receipt_number │◄──────│ ReceiptLine  │
    │ receipt_type   │  1..* │──────────────│
    │ total_amount   │       │ product      │
    │ currency       │       │ quantity     │
    │ global_number  │       │ unit_price   │
    │ hash_value     │       │ line_total   │
    │ signature      │       │ tax_amount   │
    │ qr_code        │       │ tax_type ────┼──► Taxes
    │ submitted      │       └──────────────┘
    │ payment_terms  │
    │ buyer ─────────┼──► Buyer
    └────────────────┘
```

### Model Reference

#### `Device`
The root entity. Every other model links back to it.

| Field | Type | Notes |
|-------|------|-------|
| `org_name` | CharField | Organisation name |
| `device_id` | CharField | Unique. Assigned by ZIMRA |
| `activation_key` | CharField | Used during registration |
| `device_model_name` | CharField | Sent as HTTP header to FDMS |
| `device_model_version` | CharField | Sent as HTTP header to FDMS |
| `device_serial_number` | CharField | |
| `production` | BooleanField | Switches FDMS URL test ↔ production |

#### `Certs`
Stores the device's X.509 certificate and RSA private key. OneToOne with Device.

| Field | Type | Notes |
|-------|------|-------|
| `csr` | TextField | PEM-encoded Certificate Signing Request |
| `certificate` | TextField | PEM-encoded X.509 certificate from ZIMRA |
| `certificate_key` | TextField | PEM-encoded RSA private key — **never expose** |
| `production` | BooleanField | Whether this is a production cert |

> ⚠️ **Security:** `certificate_key` is stored plaintext. Encryption at rest is planned for v0.1.7. Do not expose via API or logs.

#### `FiscalDay`
One row per trading day. Only one can be `is_open=True` per device at a time.

| Field | Type | Notes |
|-------|------|-------|
| `day_no` | IntegerField | Sourced from FDMS (`lastFiscalDayNo + 1`) |
| `receipt_counter` | IntegerField | Increments on each submitted receipt |
| `is_open` | BooleanField | Exactly one open day per device |

Constraint: `unique_together = (device, day_no)`.  
Index: `(device, is_open)` — used on every receipt submission.

#### `FiscalCounter`
Accumulates running totals per tax group or payment method within a fiscal day.

| Field | Type | Notes |
|-------|------|-------|
| `fiscal_counter_type` | CharField | See counter type enum below |
| `fiscal_counter_currency` | CharField | `USD` or `ZWG` |
| `fiscal_counter_tax_id` | IntegerField | Null for BalanceByMoneyType |
| `fiscal_counter_tax_percent` | DecimalField | Null for exempt and BalanceByMoneyType |
| `fiscal_counter_money_type` | CharField | Only for BalanceByMoneyType |
| `fiscal_counter_value` | DecimalField | Running total, can be negative |

Counter type enum (ZIMRA spec section 5.4.4):

| Value | Enum order | Tracks |
|-------|-----------|--------|
| `SaleByTax` | 0 | Sales amount per tax |
| `SaleTaxByTax` | 1 | Tax amount from sales |
| `CreditNoteByTax` | 2 | Credit note amounts (negative) |
| `CreditNoteTaxByTax` | 3 | Tax from credit notes (negative) |
| `DebitNoteByTax` | 4 | Debit note amounts |
| `DebitNoteTaxByTax` | 5 | Tax from debit notes |
| `BalanceByMoneyType` | 6 | Total by payment method |

#### `Receipt`

| Field | Type | Notes |
|-------|------|-------|
| `receipt_number` | CharField | `R-{global_number:08d}`. Unique |
| `receipt_type` | CharField | `fiscalinvoice` / `creditnote` / `debitnote` |
| `total_amount` | DecimalField | Negative for credit notes |
| `global_number` | IntegerField | From FDMS `lastReceiptGlobalNo + 1` |
| `hash_value` | CharField | SHA-256 of signature string, base64 |
| `signature` | TextField | RSA signature, base64 |
| `qr_code` | ImageField | PNG saved to `Zimra_qr_codes/` |
| `code` | CharField | 16-char verification code from signature |
| `zimra_inv_id` | CharField | FDMS-assigned receipt ID |
| `submitted` | BooleanField | False if queued offline |

#### `Taxes`
Synced from FDMS on every `open_day()` and `init_device`. Do not edit manually.

---

## 5. Receipt Processing Pipeline

```
POST /receipts/
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  ReceiptView.post()                                             │
│  Get device → call ReceiptService                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  ReceiptService.create_and_submit_receipt()  @transaction.atomic│
│                                                                 │
│  1. Inject device ID into payload                               │
│  2. ReceiptCreateSerializer.is_valid()                          │
│     ├─ Validate receipt type, currency, amounts                 │
│     ├─ Credit note: check reference exists, amount sign         │
│     └─ Buyer TIN: must be 10 digits if provided                 │
│  3. serializer.save()  → Receipt + ReceiptLine rows created     │
│  4. Re-fetch with select_related + prefetch_related             │
│  5. ZIMRAReceiptHandler.process_and_submit()                    │
│                                                                 │
│  ┌ If ReceiptSubmissionError raised ──────────────────────────┐ │
│  │ @transaction.atomic rolls back Receipt + ReceiptLine rows  │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  ZIMRAReceiptHandler.process_and_submit()                       │
│                                                                 │
│  ┌─ _ensure_fiscal_day_open() ──────────────────────────────┐  │
│  │  Query FiscalDay.is_open=True                            │  │
│  │  If none: OpenDayService.open_day() → auto-open          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ _get_next_global_number() ──────────────────────────────┐  │
│  │  GET /getStatus → lastReceiptGlobalNo                    │  │
│  │  Compare with local last → log warning if mismatch       │  │
│  │  Return fdms_last + 1                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ _build_receipt_data() ──────────────────────────────────┐  │
│  │  Build receiptLines list                                 │  │
│  │  Calculate tax groups (salesAmountWithTax, taxAmount)    │  │
│  │  Build receiptTaxes list                                 │  │
│  │  Resolve previousReceiptHash (chain)                     │  │
│  │  generate_receipt_signature_string() → signature_string  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ ZIMRACrypto.generate_receipt_hash_and_signature() ──────┐  │
│  │  hash = base64(SHA256(signature_string))                 │  │
│  │  sig  = base64(RSA_SIGN(signature_string, private_key))  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ _generate_qr_code() ────────────────────────────────────┐  │
│  │  verification_code = MD5(signature_bytes)[:16]           │  │
│  │  qr_url = {fdms_base}/{device_id}{date}{global_no}{code} │  │
│  │  Save PNG to receipt.qr_code                             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ _update_fiscal_counters() ──────────────────────────────┐  │
│  │  For each tax group in receiptTaxes:                     │  │
│  │    FiscalCounter get_or_create → F() increment           │  │
│  │  BalanceByMoneyType += paymentAmount                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ _submit_to_fdms() ──────────────────────────────────────┐  │
│  │  POST /SubmitReceipt                                     │  │
│  │  On success: FiscalDay.receipt_counter += 1              │  │
│  │  Return FDMS response (receiptID, serverSignature, etc.) │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
                  receipt.submitted = True
                  receipt.zimra_inv_id = ...
                  receipt.save()
                  Return 201
```

---

## 6. Fiscal Day Lifecycle

```
                    ┌──────────────────────────────┐
                    │   No open fiscal day (start)  │
                    └──────────────┬───────────────┘
                                   │
                      POST /open-day/  or  auto-open
                                   │
                    ┌──────────────▼───────────────┐
                    │     OpenDayService.open_day() │
                    │                               │
                    │  GET /getStatus               │
                    │   → lastFiscalDayNo           │
                    │  next_day_no = last + 1       │
                    │                               │
                    │  POST /openDay {              │
                    │    fiscalDayNo: N,            │
                    │    fiscalDayOpened: datetime  │
                    │  }                            │
                    │                               │
                    │  FiscalDay.objects.create(    │
                    │    day_no=N, is_open=True     │
                    │  )                            │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   Fiscal Day OPEN             │
                    │   is_open = True              │
                    │   receipt_counter = 0         │
                    │                               │
                    │   ← receipts submitted        │
                    │   ← counters accumulate       │
                    │   ← receipt_counter++         │
                    └──────────────┬───────────────┘
                                   │
                      POST /close-day/
                                   │
                    ┌──────────────▼───────────────┐
                    │  ClosingDayService.close_day()│
                    │                               │
                    │  Build counter string         │
                    │  Assemble closing string      │
                    │  SHA-256 + RSA sign           │
                    │                               │
                    │  POST /CloseDay { payload }   │
                    │                               │
                    │  sleep(10)                    │
                    │  GET /getStatus               │
                    │   → fiscalDayStatus           │
                    └──────────────┬───────────────┘
                                   │
               ┌───────────────────┼──────────────────────┐
               │                   │                       │
    FiscalDayClosed      FiscalDayCloseFailed        Unexpected
               │                   │                       │
    is_open=False           raise CloseDayError     raise CloseDayError
    return status           (day stays open,        
                            retry allowed)          
```

### Day No Resolution

`OpenDayService` always defers to FDMS for the authoritative day number:

```
GET /getStatus → lastFiscalDayNo = N

Local last day_no == N ?
  Yes → proceed, next = N + 1
  No  → log WARNING "Local/FDMS day_no mismatch", still use N + 1
```

---

## 7. Closing Day & Signature Spec

Per ZIMRA API spec section 13.3.1.

### Closing String Assembly

```
closing_string = (
    str(device.device_id)
  + str(fiscal_day.day_no)
  + fiscal_day.created_at.strftime("%Y-%m-%d")   ← day OPEN date, not today
  + sale_by_tax_string
  + sale_tax_by_tax_string
  + credit_note_by_tax_string
  + credit_note_tax_by_tax_string
  + balance_by_money_type_string
).upper()
```

> ⚠️ **Critical:** `fiscalDayDate` must be the date the day was **opened**, not today's date. Using today's date causes `CountersMismatch` if the day spans midnight.

### Counter String Format

Each counter line: `TYPE + CURRENCY + [TAX_PERCENT or MONEY_TYPE] + VALUE_IN_CENTS`

```
SALEBYTAXUSD15.00115000
SALEBYTAXUSD0.005000
SALEBYTAXUSDEXEMPT_NOTREALFIELD    ← exempt: empty tax part
SALEBYTAXUSD67475                  ← exempt example (empty between USD and value)
BALANCEBYMONEYTYPEUSDLCASH69975    ← note the L between currency and money type
BALANCEBYMONEYTYPEZWGLCARD69975
```

**Rules:**

| Rule | Detail |
|------|--------|
| All uppercase | `.upper()` applied to entire string |
| Amounts in cents | `int(round(value * 100))` — preserves sign |
| Tax percent format | Always two decimal places: `15` → `15.00`, `0` → `0.00`, `14.5` → `14.50` |
| Exempt tax percent | Empty string — nothing between currency and value |
| BalanceByMoneyType | Literal `L` between currency and money type (`USDLCASH`, `ZWGLCARD`) |
| Zero-value counters | Excluded entirely (spec section 4.11) |
| Sort order | Type enum ASC → currency alpha ASC → taxID/moneyType ASC |

### Sort Order (spec section 13.3.1)

```
FiscalCounterType enum order:
  SaleByTax(0) → SaleTaxByTax(1) → CreditNoteByTax(2) →
  CreditNoteTaxByTax(3) → DebitNoteByTax(4) →
  DebitNoteTaxByTax(5) → BalanceByMoneyType(6)

Within each type:
  currency ASC (USD before ZWG)
  taxID ASC (for byTax)  /  moneyType ASC alpha (for BalanceByMoneyType)
```

### Signature Generation

```
hash      = base64( SHA256( closing_string.encode("utf-8") ) )
signature = base64( RSA_PKCS1v15_SIGN( closing_string, private_key ) )

payload = {
  "fiscalDayDeviceSignature": {
    "hash": hash,
    "signature": signature
  }
}
```

### Common Close Day Errors

| Error | Root cause |
|-------|-----------|
| `CountersMismatch` | Wrong date, missing `L`, wrong tax percent format, unsorted counters, zero counters included |
| `BadCertificateSignature` | Certificate expired / wrong private key used |
| `FiscalDayCloseFailed` | FDMS validation failed — check `fiscalDayClosingErrorCode` |

---

## 8. Cryptography

### ZIMRACrypto

**Location:** `zimra_crypto.py`

**Library:** `cryptography` (replaces deprecated `pyOpenSSL`)

```
┌──────────────────────────────────────────────────────┐
│                    ZIMRACrypto                        │
│                                                      │
│  private_key_path ──► CertTempManager               │
│                         (temp file from Certs model) │
│                                                      │
│  load_private_key() ──► RSAPrivateKey (cached)       │
│                                                      │
│  get_hash(data) ──► SHA256(data) → base64            │
│                                                      │
│  sign_data(data) ──► RSA PKCS1v15 → base64           │
│                                                      │
│  generate_receipt_hash_and_signature(string)         │
│    → { hash: str, signature: str }                   │
│                                                      │
│  generate_verification_code(signature_b64)           │
│    → MD5(sig_bytes).hexdigest()[:16].upper()         │
│    → formatted as XXXX-XXXX-XXXX-XXXX               │
│                                                      │
│  generate_key_and_csr(device)                        │
│    → RSA 2048 key pair                               │
│    → CSR with CN=ZIMRA-{serial}-{device_id}          │
└──────────────────────────────────────────────────────┘
```

### Receipt Signature String

Per ZIMRA spec section 13.2.1:

```
{deviceID}
{receiptType}            ← UPPERCASE e.g. FISCALINVOICE
{receiptCurrency}        ← UPPERCASE e.g. USD
{receiptGlobalNo}
{receiptDate}            ← YYYY-MM-DDTHH:mm:ss
{receiptTotal_in_cents}  ← negative for credit notes
{receiptTaxes}           ← concatenated, ordered by taxID ASC
{previousReceiptHash}    ← omitted if first receipt of day
```

Tax line format: `taxCode + taxPercent + taxAmount_cents + salesAmountWithTax_cents`

### Private Key Lifecycle

```
init_device
    │
    ▼
ZIMRACrypto.generate_key_and_csr()
    │  RSA 2048 key pair generated in memory
    │  CSR built and signed
    │
    ▼
ZIMRAClient.register_device()
    │  CSR sent to FDMS
    │  Signed certificate returned
    │
    ▼
Certs.objects.create(
    csr=csr_pem,
    certificate=cert_pem,
    certificate_key=private_key_pem
)
    │
    ▼
ZIMRACrypto (at runtime)
    │
    ▼
CertTempManager
    │  Writes cert + key to tempfile.mkdtemp()
    │  Returns path for load_private_key()
    │
    ▼
ZIMRAClient.session.cert = pem_path   ← mTLS
    │
    ▼
ZIMRAClient.close() / __del__
    │  shutil.rmtree(temp_dir)         ← cleanup
```

---

## 9. ZIMRA Client

### ZIMRAClient

**Location:** `zimra_base.py`

```
┌───────────────────────────────────────────────────────┐
│                     ZIMRAClient                        │
│                                                       │
│  __init__(device)                                     │
│    ├─ Load Configuration (cached @property)           │
│    ├─ Load Certs (cached @property)                   │
│    ├─ Set base_url / public_url based on production   │
│    ├─ Write temp PEM from Certs                       │
│    └─ Create requests.Session with cert + headers     │
│                                                       │
│  Endpoints:                                           │
│  ┌─────────────────────────────────────────────────┐ │
│  │ register_device(payload)  → public, no cert     │ │
│  │ get_status()              → GET /getStatus      │ │
│  │ get_config()              → GET /getConfig      │ │
│  │ ping()                    → POST /ping          │ │
│  │ open_day(payload)         → POST /openDay       │ │
│  │ close_day(payload)        → POST /CloseDay      │ │
│  │ submit_receipt(payload)   → POST /SubmitReceipt │ │
│  │ issue_certificate(payload)→ POST /issueCert     │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  _request(method, endpoint)                           │
│    ├─ Build full URL                                  │
│    ├─ session.request(timeout=30)                     │
│    ├─ response.raise_for_status()                     │
│    └─ On error: log + re-raise requests.RequestException│
│                                                       │
│  Lifecycle:                                           │
│  close() → session.close() + rmtree(temp_dir)        │
│  __enter__ / __exit__ → context manager              │
│  __del__ → close() on GC                             │
└───────────────────────────────────────────────────────┘
```

### URLs

| Environment | Device API | Public API |
|-------------|-----------|-----------|
| Testing | `https://fdmsapitest.zimra.co.zw/Device/v1/{device_id}` | `https://fdmsapitest.zimra.co.zw/Public/v1/{device_id}` |
| Production | `https://fdmsapi.zimra.co.zw/Device/v1/{device_id}` | `https://fdmsapi.zimra.co.zw/Public/v1/{device_id}` |

All Device API requests use mutual TLS. The Public API (`RegisterDevice`) uses plain HTTPS with no client cert.

---

## 10. Fiscal Counters

### Update Flow (per receipt)

```
ZIMRAReceiptHandler._update_fiscal_counters_inner()

For each tax group in receiptTaxes:
│
├─ receipt_type == "fiscalinvoice"
│   ├─ SaleByTax      += salesAmountWithTax  (per tax group)
│   └─ SaleTaxByTax   += taxAmount           (non-exempt, non-zero only)
│
├─ receipt_type == "creditnote"
│   ├─ CreditNoteByTax    += -salesAmountWithTax  (negative)
│   └─ CreditNoteTaxByTax += -taxAmount           (negative, non-exempt, non-zero)
│
└─ receipt_type == "debitnote"
    ├─ DebitNoteByTax    += salesAmountWithTax
    └─ DebitNoteTaxByTax += taxAmount

Always (all types):
  BalanceByMoneyType += paymentAmount   (negative for credit notes)
```

### Race Condition Prevention

Counter updates use Django `F()` expressions for atomic DB-level increments, preventing lost updates under concurrent receipt submission:

```python
# Instead of:
counter.fiscal_counter_value += amount   # ← race condition
counter.save()

# FiscGuy uses:
FiscalCounter.objects.filter(...).update(
    fiscal_counter_value=F("fiscal_counter_value") + amount
)
```

### get_or_create Key

Each unique combination gets its own row:

```python
FiscalCounter.objects.get_or_create(
    fiscal_counter_type=counter_type,
    fiscal_counter_currency=currency,
    fiscal_counter_tax_id=tax_id,
    fiscal_counter_tax_percent=tax_percent,
    fiscal_counter_money_type=money_type,
    fiscal_day=fiscal_day,
    defaults={"fiscal_counter_value": amount},
)
```

---

## 11. Error Handling

### Exception Hierarchy

```
FiscalisationError
├── ReceiptSubmissionError   Receipt can't be processed or submitted
├── CloseDayError            Day close rejected by FDMS
├── FiscalDayError           Day open failed
├── ConfigurationError       Config missing or sync failed
├── CertificateError         Cert issuance/renewal failed
├── DevicePingError          Ping to FDMS failed
├── StatusError              Status fetch failed
├── DeviceRegistrationError  Registration with ZIMRA failed
├── CryptoError              RSA/hash operation failed
├── CertNotFoundError        No cert found in DB
├── PersistenceError         DB write failed
├── ZIMRAAPIError            Generic FDMS API error
├── ValidationError          Data validation failed
├── AuthenticationError      mTLS auth failed
├── TaxError                 Tax CRUD failed
├── DeviceNotFoundError      Device not in DB
├── ZIMRAClientError         Client-level failure
└── TenantNotFoundError      Multi-tenant lookup failed
```

### View Error Mapping

```
ReceiptSubmissionError  → 422 Unprocessable Entity
CloseDayError           → 422 Unprocessable Entity
FiscalDayError          → 400 Bad Request
ConfigurationError      → 500 Internal Server Error
CertificateError        → 422 Unprocessable Entity
DevicePingError         → 500 Internal Server Error
StatusError             → 500 Internal Server Error
No device found         → 404 Not Found
No open fiscal day      → 400 Bad Request
Exception (catch-all)   → 500 Internal Server Error
```

---

## 12. Database Design

### Indexes

```
Device:
  device_id                        UNIQUE

FiscalDay:
  (device_id, day_no)              UNIQUE
  (device_id, is_open)             INDEX  ← every receipt submission queries this

FiscalCounter:
  (device_id, fiscal_day_id)       INDEX

Receipt:
  receipt_number                   UNIQUE
  (device_id, -created_at)         INDEX  ← paginated receipt listing

ReceiptLine:
  (receipt_id)                     INDEX

Taxes:
  (tax_id)                         INDEX  ← looked up on every receipt line

Buyer:
  (tin_number)                     INDEX
```

### Query Patterns

| Operation | Query |
|-----------|-------|
| Get open fiscal day | `FiscalDay.objects.filter(device=d, is_open=True).first()` |
| Get open day (with lock) | `select_for_update().filter(device=d, is_open=True).first()` |
| Get receipt with lines | `select_related("buyer").prefetch_related("lines")` |
| Build tax map | `{t.tax_id: t.name for t in Taxes.objects.all()}` |
| Upsert counter | `get_or_create(...)` then `F()` update |

---

## 13. Development Guidelines

### Adding a New Service

1. Create `fiscguy/services/my_service.py`
2. Accept `device: Device` in `__init__`
3. Raise typed `FiscalisationError` subclasses — never raw `Exception`
4. Wrap DB writes in `transaction.atomic`
5. Add a view in `views.py` and route in `urls.py`
6. Add tests in `fiscguy/tests/`

```python
class MyService:
    def __init__(self, device: Device):
        self.device = device
        self.client = ZIMRAClient(device)

    @transaction.atomic
    def do_thing(self) -> dict:
        try:
            result = self.client.some_endpoint()
        except requests.RequestException as exc:
            raise MyError("FDMS call failed") from exc

        MyModel.objects.create(device=self.device, ...)
        return result
```

### Adding a New Endpoint

```python
# views.py
class MyView(APIView):
    def post(self, request):
        device = Device.objects.first()
        if not device:
            return Response({"error": "No device registered"}, status=404)
        try:
            result = MyService(device).do_thing()
            return Response(result, status=200)
        except MyError as exc:
            logger.error(f"My thing failed: {exc}")
            return Response({"error": str(exc)}, status=422)
        except Exception:
            logger.exception("Unexpected error")
            return Response({"error": "Internal server error"}, status=500)

# urls.py
path("my-endpoint/", MyView.as_view(), name="my-endpoint"),
```

### Logging

Use `loguru`. Follow these levels:

| Level | When |
|-------|------|
| `logger.info()` | Normal operations — receipt submitted, day opened |
| `logger.warning()` | Recoverable issues — FDMS/local mismatch, offline queue |
| `logger.error()` | Handled failures — receipt rejected, close failed |
| `logger.exception()` | Unexpected errors — always in `except` blocks, includes traceback |

Never log private keys, raw certificates, or full receipt payloads at INFO level.

### Migrations

```bash
# After model changes
python manage.py makemigrations fiscguy

# Apply
python manage.py migrate

# Never edit existing migrations
# Always create a new migration for changes
```

### Testing

```bash
pytest                                          # all tests
pytest --cov=fiscguy --cov-report=html         # with coverage
pytest fiscguy/tests/test_closing_day_service.py # single file
pytest -k "test_build_sale_by_tax"              # single test
```

Mock external calls at the boundary — patch `ZIMRAClient`, `ZIMRACrypto`, and `requests`. Never make real FDMS calls in tests.

```python
@patch("fiscguy.services.open_day_service.ZIMRAClient")
def test_open_day_success(self, MockClient):
    MockClient.return_value.get_status.return_value = {"lastFiscalDayNo": 5}
    MockClient.return_value.open_day.return_value = {"fiscalDayNo": 6}
    ...
```

### Code Style

- Line length: 100 (Black)
- Imports: isort with Black profile
- Private methods: prefix `_`
- Type hints on all public method signatures
- Docstrings on all public classes and methods

```bash
black fiscguy && isort fiscguy && flake8 fiscguy && mypy fiscguy
```

---

> **Internal use only.** Do not publish this document.  
> Maintainer: Casper Moyo · cassymyo@gmail.com  
> Version: 0.1.6 · April 2026
