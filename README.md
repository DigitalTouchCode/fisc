# fiscguy

fiscguy is a Django/DRF-powered library for integrating ZIMRA fiscal devices with your applications. It centralizes device provisioning, receipt submission, fiscal-day lifecycle management, and synchronization of the ZIMRA-issued tax catalogue.

---

## Feature Highlights

- Interactive **device on-boarding** (CSR generation + certificate registration)
- **Receipt orchestration** for fiscal invoices and credit notes
- **Fiscal day** open/close utilities with ZIMRA FDMS
- **Configuration & tax synchronization** with authoritative ZIMRA data
- Extensible service layer for custom workflows

---

## Project Layout

```
fiscguy/
├── management/commands/init_device.py   # Interactive device provisioning
├── models.py                            # Device, Receipt, FiscalDay, Taxes, Certs, etc.
├── serializers.py                       # DRF serializers for receipts/config/taxes
├── services/
│   ├── closing_day_service.py           # Builds payload for closing fiscal day
│   └── receipt_service.py               # Receipt creation + submission logic
├── urls.py                              # DRF endpoint wiring
├── views.py                             # REST endpoints for receipts, days, config, taxes
├── zimra_base.py                        # Low-level FDMS HTTP client
├── zimra_receipt_handler.py             # Formatting + signing of receipt payloads
└── zimra_crypto.py                       # Cryptographic toolkit for receipts and device provisioning
```

---

## ZIMRA Integration Classes

| Module | Description |
|--------|-------------|
| `fiscguy/zimra_base.py` (`ZIMRAClient`) | Boots a requests session pinned to the device certificate, builds environment-specific base URLs, and exposes primitives such as `open_day`, `close_day`, `get_status`, `get_config`, and `submit_receipt`. It also manages PEM file lifecycle and enforces that configuration/certs exist before any FDMS call. |
| `fiscguy/zimra_receipt_handler.py` (`ZIMRAReceiptHandler`) | High-level orchestrator for fiscal documents. Generates FDMS-compliant payloads (including line/tax aggregation), calculates hash & signature strings, submits receipts via `ZIMRAClient`, maintains fiscal counters, stores QR artifacts, and differentiates between `FiscalInvoice` and `CreditNote` flows. |
| `fiscguy/zimra_crypto.py` (`ZIMRACrypto`) | Encapsulates hashing, RSA signing, verification-code generation, and CSR/private-key provisioning. Exposes helpers to build the signature string, compute hash+signature pairs, and bootstrap device certificates during onboarding. |

### Utility Helpers

| Module | Purpose |
|--------|---------|
| `fiscguy/utils/datetime_now.py` | Provides `datetime_now()` and `date_today()` helpers that always emit timestamps in the `Africa/Harare` timezone—matching ZIMRA’s expected clock. Used across device registration, receipt payloads, and fiscal day operations. |
| `fiscguy/utils/cert_temp_manager.py` | Manages certificate PEM material pulled from the database by writing it to thread-safe temporary files and cleaning them up once the request lifecycle ends. This underpins both `ZIMRAClient` and `ZIMRACrypto` so the library never leaves long-lived certificate files on disk. |

### How they collaborate
1. `ZIMRAReceiptHandler.generate_receipt_data` prepares the payload and asks `ZIMRACrypto` for hash/signature material.
2. `ZIMRAClient.submit_receipt` transports the signed payload to ZIMRA FDMS and returns the authoritative response.
3. The handler then updates QR codes, verification codes, and fiscal counters so local state mirrors FDMS.

---

## Device Registration Workflow

Run the management command to register and configure a device:

```bash
python manage.py init_device
```

Input requested:
- Environment (`yes` = production, `no` = test)
- Organisation name
- Device ID
- Serial number
- Activation key
- Device model name & version

What it does:
1. Persists/updates `Device`
2. Generates CSR, registers device, stores signed cert in `Certs`
3. Pulls configuration + taxes from FDMS, writing to `Configuration` & `Taxes`

---

## REST API

All endpoints live under the `fiscguy` namespace (`fiscguy/urls.py`).

### 1. Receipts

#### Submit Receipt
`POST /receipts/`

**Fiscal Invoice Payload**
```json
{
  "receipt_type": "fiscalinvoice",
  "currency": "USD",
  "total_amount": 100.0,
  "payment_terms": "cash",
  "lines": [
    {
      "product": "Premium Support",
      "quantity": 2,
      "unit_price": 50.0,
      "line_total": 100.0,
      "tax_name": "standard rated 15.5%"
    }
  ]
}
```
> **Required fields:** `credit_note_reference` and `credit_note_reason` must always be provided for every credit note submission so ZIMRA can link the reversal to the original invoice and audit trail.

**Credit Note Payload (amounts MUST be negative)**
```json
{
  "receipt_type": "creditnote",
  "currency": "USD",
  "total_amount": -15.0,
  "credit_note_reference": "R-000344", // reference to the original invoice #receipt number
  "credit_note_reason": "cancel",
  "payment_terms": "cash",
  "lines": [
    {
      "product": "test product",
      "quantity": 1,
      "unit_price": -15.0,
      "line_total": -15.0,
      "tax_name": "standard rated 15.5%"
    }
  ]
}
```

**Successful Response (201)**
```json
{
  "id": 346,
  "lines": [
    {
      "id": 482,
      "product": "test product",
      "quantity": 1,
      "unit_price": 15.0,
      "line_total": 15.0,
      "tax_amount": 0.0
    }
  ],
  "buyer": null,
  "receipt_number": "R-000346",
  "receipt_type": "fiscalinvoice",
  "total_amount": 15.0,
  "qr_code": "/Zimra_qr_codes/qr_R-000346.png",
  "code": "C223844AC02AED83",
  "currency": "USD",
  "global_number": 805,
  "hash_value": "beZfXbCddqRUil1dlm7Ivh4uokhENXgmkb1xXvxymVw=",
  "signature": "IoFJn6CAxdJlDFf1JbC7Nrc+w1rePQyo89n9jfrego6x4ytbBIeWrlUR28Liiia21T4VUO13e/o6pZOtaYdSnehUUkTErfmZ7NSzJSPoEV11UhSb9duSjuOrU7Wrqymhtru0/IqJKY1p4JtLJNDS/tQQR5aqOoP7lgqoxLPKPJwfCdT2QbUaaRi67E9ShbQQtqonTWZmCMC32p89YzHfmRcpdlCnCMSAaj1ISMpfi/VZtUCFFQYJssMQSI8Ou1HZ2Bib+TpxZPWRhMQdOWOIjqWvhqPXtOrjd/xuyM2Fdujfs6FtiLZKLJXwH46Xgcg9yD/0wtVwaKKzFxlUgNPSmw==",
  "created_at": "2026-02-05T20:11:57.126420Z",
  "updated_at": "2026-02-05T20:11:57.126456Z",
  "zimra_inv_id": "10663582",
  "payment_terms": "cash",
  "submitted": true,
  "is_credit_note": false,
  "credit_note_reason": "cancel",
  "credit_note_reference": "R-000344"
}
```
> `credit_note_reference` and `credit_note_reason` appear only when the receipt represents a credit note (`is_credit_note: true`).

#### Retrieve Receipt
`GET /receipts/{id}/`

Returns the serialized receipt, including lines, buyer, submission metadata.

---

### 2. Fiscal Day Operations

| Endpoint        | Method | Description                            |
|-----------------|--------|----------------------------------------|
| `/open-day/`    | GET    | Opens the fiscal day via FDMS          |
| `/close-day/`   | GET    | Aggregates counters and closes the day |
| `/get-status/`  | GET    | Returns current fiscal day status      |

`/close-day/` leverages `ClosingDayService` to build the closing payload (counters, taxes, totals), submits it to ZIMRA, and returns the refreshed status.

---

### 3. Configuration

`GET /configuration/` – Returns the stored `Configuration` snapshot pulled from FDMS during device registration.

---

### 4. Tax Management (Tax Mapping)

`GET /taxes/` – Lists the ZIMRA-provided tax catalogue.

```json
[
  {
    "tax_id": "517", 
    "name": "standard rated 15.5%",
    "rate": 15.5,
    "is_active": true
  },
  {
    "tax_id": "2",
    "name": "zero rated 0%",
    "rate": 0.0,
    "is_active": true
  }
]
```

**Important**
1. `tax_id` values originate from ZIMRA and are read-only
2. `tax_name` in receipt lines must match the stored mapping exactly
3. Only active taxes (`is_active: true`) should be referenced; invalid mappings cause FDMS rejection

---

## Setup & Usage

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py init_device
```

Daily flow:
1. `GET /open-day/`
2. Submit receipts as they occur
3. `GET /close-day/` before shutdown

---

## Error Contract

Errors follow a simple shape:
```json
{
  "error": "Human-readable description"
}
```
HTTP status codes align with the failure condition (400 validation, 401 auth, 500 internal, etc.).

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Add/adjust tests where relevant
4. Submit a PR describing the change

---

## License

MIT License

---

Developed by Casper Moyo – Property of DT  
Version 1.0.0
