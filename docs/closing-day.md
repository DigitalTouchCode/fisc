# Closing a Fiscal Day

At the end of each trading day, the fiscal day must be closed by submitting a signed summary of all fiscal counters to ZIMRA FDMS.

---

## Quick Close

```python
from fiscguy import close_day

result = close_day()
# {"fiscalDayStatus": "FiscalDayClosed", ...}
```

Or via REST:

```
POST /fiscguy/close-day/
```

---

## What Happens During Close

`ClosingDayService.close_day()` performs these steps in order:

1. **Build counter strings** — each counter type is serialised into the ZIMRA closing string format
2. **Assemble the closing string** — `deviceID + fiscalDayNo + fiscalDayDate + counters`
3. **Hash and sign** — SHA-256 hash of the string, signed with the device RSA private key
4. **Build payload** — closing string, signature, fiscal day counters, receipt counter
5. **Submit to FDMS** — `POST /CloseDay`
6. **Poll for status** — waits 10 seconds then calls `GET /getStatus`
7. **Update database** — marks `FiscalDay.is_open = False` on success

---

## Closing String Specification

From ZIMRA API spec section 13.3.1. Fields concatenated in this exact order:

| Order | Field | Format |
|-------|-------|--------|
| 1 | `deviceID` | Integer as-is |
| 2 | `fiscalDayNo` | Integer as-is |
| 3 | `fiscalDayDate` | `YYYY-MM-DD` — **date the fiscal day was opened**, not today |
| 4 | `fiscalDayCounters` | Concatenated counter string (see below) |

All text **uppercase**. No separators between fields.

### Counter String

Each counter line: `TYPE || CURRENCY || [TAX_PERCENT or MONEY_TYPE] || VALUE_IN_CENTS`

**Sort order:**
1. Counter type — ascending by enum value (`SaleByTax=0` → `BalanceByMoneyType=6`)
2. Currency — alphabetical ascending
3. TaxID — ascending (for byTax types) / MoneyType — ascending (for BalanceByMoneyType)

**Tax percent formatting:**
- Integer percent: always two decimals — `15` → `15.00`, `0` → `0.00`
- Decimal percent: `14.5` → `14.50`
- Exempt (no percent): empty string — nothing between currency and value

**BalanceByMoneyType:** has a literal `L` between currency and money type:

```
BALANCEBYMONEYTYPEUSDLCASH3700
BALANCEBYMONEYTYPEZWGLCARD1500000
BALANCEBYMONEYTYPEZWGLCASH2000000
```

**Zero-value counters:** excluded entirely (per spec section 4.11).

**Amounts:** in cents, preserving sign. `-699.75` → `-69975`.

### Full Example

From ZIMRA spec section 13.3.1:

```
321842019-09-23
SALEBYTAXZWL2300000
SALEBYTAXZWL0.001200000
SALEBYTAXUSD14.502500
SALEBYTAXZWL15.001200
SALETAXBYTAXUSD15.00250
SALETAXBYTAXZWL15.00230000
BALANCEBYMONEYTYPEUSDLCASH3700
BALANCEBYMONEYTYPEZWLCASH2000000
BALANCEBYMONEYTYPEZWLCARD1500000
```

Hash (SHA-256, base64): `OdT8lLI0JXhXl1XQgr64Zb1ltFDksFXThVxqM6O8xZE=`

---

## Common Close Day Errors

### `CountersMismatch`

FDMS computed different counter values from what was submitted.

**Causes:**
- `fiscalDayDate` in the closing string uses today's date instead of the fiscal day open date
- Tax percent not formatted as two decimal places (`15` instead of `15.00`)
- `BalanceByMoneyType` missing the `L` separator
- Counters not sorted in the correct order
- Credit note counter not negated, or using `receiptTotal` instead of per-tax `salesAmountWithTax`
- Zero-value counters included in the payload

### `BadCertificateSignature`

FDMS cannot verify the device signature.

**Causes:**
- Wrong private key used for signing (key doesn't match the registered certificate)
- Certificate has expired — run `POST /fiscguy/issue-certificate/`
- Certificate has been revoked

### `FiscalDayCloseFailed`

FDMS accepted the request but validation failed. The day remains open and can be retried.

Check `fiscalDayClosingErrorCode` in the response for the specific reason.

---

## Fiscal Day Status Values

| Status | Meaning |
|--------|---------|
| `FiscalDayOpened` | Day is open, receipts can be submitted |
| `FiscalDayCloseInitiated` | Close request submitted, processing |
| `FiscalDayClosed` | Day closed successfully |
| `FiscalDayCloseFailed` | Close attempt failed — day remains open, retry allowed |

---

## Retrying a Failed Close

If `close_day()` raises `CloseDayError` with `FiscalDayCloseFailed`, the day remains open and you can correct the issue and retry:

```python
from fiscguy import close_day
from fiscguy.exceptions import CloseDayError

try:
    close_day()
except CloseDayError as e:
    print(f"Close failed: {e}")
    # Investigate, fix, then retry:
    close_day()
```

FDMS allows close retries when the fiscal day status is `FiscalDayOpened` or `FiscalDayCloseFailed`.
