# Error Reference

All FiscGuy exceptions inherit from `FiscalisationError`. Import them from `fiscguy.exceptions`.

---

## Exception Hierarchy

```
FiscalisationError
├── ReceiptSubmissionError
├── CloseDayError
├── FiscalDayError
├── ConfigurationError
├── CertificateError
├── DevicePingError
├── StatusError
├── DeviceRegistrationError
├── CryptoError
├── CertNotFoundError
├── PersistenceError
├── ZIMRAAPIError
├── ValidationError
├── AuthenticationError
├── TaxError
├── DeviceNotFoundError
├── TenantNotFoundError
└── ZIMRAClientError
```

---

## Common Exceptions

### `ReceiptSubmissionError`

Raised when a receipt cannot be processed or submitted.

```python
from fiscguy.exceptions import ReceiptSubmissionError

try:
    submit_receipt(data)
except ReceiptSubmissionError as e:
    print(e)
```

Common causes:
- No open fiscal day — call `open_day()` first
- Invalid receipt data (missing required fields, wrong types)
- FDMS rejected the receipt (validation errors)
- FDMS unreachable and auto-queue failed
- Credit note references a non-existent original receipt
- Credit note amount exceeds original receipt amount

---

### `CloseDayError`

Raised when the fiscal day cannot be closed.

```python
from fiscguy.exceptions import CloseDayError

try:
    close_day()
except CloseDayError as e:
    print(e)
```

Common causes and fixes:

| Error code | Cause | Fix |
|------------|-------|-----|
| `CountersMismatch` | Closing string counters don't match FDMS records | Check closing string format — date, tax percent format, L separator |
| `BadCertificateSignature` | Device signature cannot be verified | Certificate expired or wrong key — renew certificate |
| `FiscalDayCloseFailed` | FDMS validation failed | Check `fiscalDayClosingErrorCode` in logs |
| Empty response | FDMS returned nothing | Retry after a delay |

---

### `FiscalDayError`

Raised when a fiscal day cannot be opened.

Common causes:
- A fiscal day is already open
- FDMS rejected the open request
- Previous fiscal day was not closed

---

### `ConfigurationError`

Raised when configuration is missing or sync fails.

Common causes:
- `init_device` was not run
- FDMS unreachable during configuration sync
- Configuration sync after `open_day()` failed (day opened, config not updated)

---

### `CertificateError`

Raised when certificate issuance or renewal fails.

Common causes:
- FDMS rejected the certificate request
- Device not registered with ZIMRA
- Network failure during certificate request

---

### `DevicePingError`

Raised when the device ping to FDMS fails.

---

### `StatusError`

Raised when the status fetch from FDMS fails.

---

### `DeviceRegistrationError`

Raised during `init_device` if ZIMRA rejects the registration request.

Common causes:
- Invalid activation key
- Device ID already registered
- Network failure

---

### `CryptoError`

Raised when RSA signing, hashing, or key generation fails.

---

## HTTP Status Codes (REST API)

| HTTP Status | Meaning |
|-------------|---------|
| `200 OK` | Success |
| `201 Created` | Receipt submitted successfully |
| `400 Bad Request` | Invalid request — fiscal day already open, no open day to close |
| `404 Not Found` | No device registered |
| `405 Method Not Allowed` | Wrong HTTP method |
| `422 Unprocessable Entity` | FDMS rejected the request |
| `500 Internal Server Error` | Unexpected server error |

---

## Logging

FiscGuy uses `loguru` for structured logging. All service operations log at appropriate levels:

```python
# In your Django project — configure loguru sink
from loguru import logger

logger.add("fiscguy.log", level="INFO", rotation="1 day")
```

Key log events:

| Level | Event |
|-------|-------|
| `INFO` | Receipt submitted, day opened/closed, client initialised |
| `WARNING` | FDMS offline (receipt queued), global number mismatch |
| `ERROR` | Receipt submission failed, close day failed |
| `EXCEPTION` | Unexpected errors with full traceback |
