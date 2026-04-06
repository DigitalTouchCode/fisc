# Fiscal Counters

Fiscal counters are running totals that accumulate throughout a fiscal day. At close of day they are submitted to ZIMRA as part of the closing payload and used to verify the hash signature.

---

## Counter Types

| Counter | Tracks | By Tax | By Currency | By Payment |
|---------|--------|--------|-------------|------------|
| `SaleByTax` | Total sales amount including tax | ✓ | ✓ | |
| `SaleTaxByTax` | Tax portion of sales | ✓ | ✓ | |
| `CreditNoteByTax` | Total credit note amounts | ✓ | ✓ | |
| `CreditNoteTaxByTax` | Tax portion of credit notes | ✓ | ✓ | |
| `DebitNoteByTax` | Total debit note amounts | ✓ | ✓ | |
| `DebitNoteTaxByTax` | Tax portion of debit notes | ✓ | ✓ | |
| `BalanceByMoneyType` | Total collected by payment method | | ✓ | ✓ |

---

## How Counters Are Updated

Every time a receipt is submitted, `_update_fiscal_counters_inner` runs automatically. You never need to update counters manually.

### Fiscal Invoice

```
SaleByTax        += salesAmountWithTax   (per tax group)
SaleTaxByTax     += taxAmount            (per tax group, non-exempt/non-zero only)
BalanceByMoneyType += paymentAmount      (per payment method)
```

### Credit Note

Credit note values are **negative** — each counter decreases:

```
CreditNoteByTax      += salesAmountWithTax  (negative, per tax group)
CreditNoteTaxByTax   += taxAmount           (negative, non-exempt/non-zero only)
BalanceByMoneyType   += paymentAmount       (negative)
```

### Debit Note

```
DebitNoteByTax       += salesAmountWithTax  (per tax group)
DebitNoteTaxByTax    += taxAmount           (non-exempt/non-zero only)
BalanceByMoneyType   += paymentAmount
```

---

## Counter Rows in the Database

Each unique combination of `(counter_type, currency, tax_id, tax_percent, money_type, fiscal_day)` gets its own `FiscalCounter` row. On first encounter it is created; on subsequent receipts it is incremented.

```python
from fiscguy.models import FiscalCounter, FiscalDay

day = FiscalDay.objects.filter(is_open=True).first()
counters = day.counters.all()

for c in counters:
    print(c.fiscal_counter_type, c.fiscal_counter_currency, c.fiscal_counter_value)
```

---

## Zero-Value Counters

Per ZIMRA spec (section 4.11): **zero-value counters must not be submitted** to FDMS. FiscGuy automatically excludes them from the closing payload and closing string.

---

## Closing String Format

At `close_day()`, all counters are concatenated into a single string for signing. The format per ZIMRA spec section 13.3.1:

```
{deviceID}{fiscalDayNo}{fiscalDayDate}{counters...}
```

Each counter line is:

```
{TYPE}{CURRENCY}[L]{TAX_PERCENT_OR_MONEY_TYPE}{VALUE_IN_CENTS}
```

Rules:
- All text **uppercase**
- Amounts in **cents** (multiply by 100, integer, negative for credit notes)
- Tax percent always **two decimal places** (`15.00`, `0.00`, `14.50`)
- Exempt entries use **empty string** for tax percent (nothing between currency and value)
- `BalanceByMoneyType`BALANCEBYMONEYTYPEUSDCASH3700`)
- Ordered by: counter type ascending → currency ascending → taxID/moneyType ascending

Example:

```
23265842026-03-30
SALEBYTAXZWG0.005000
SALEBYTAXZWG15.50134950
SALETAXBYTAXZWG15.5018110
BALANCEBYMONEYTYPEZWGCARD69975
BALANCEBYMONEYTYPEZWGCASH69975
```

(joined as one string, no newlines)

---

## Resetting Counters

Counters reset automatically when a fiscal day is closed. The next `open_day()` starts fresh from zero.

If you need to inspect counters mid-day:

```python
from fiscguy.models import FiscalDay, FiscalCounter

fiscal_day = FiscalDay.objects.filter(is_open=True).first()
print(fiscal_day.counters.all().values(
    "fiscal_counter_type",
    "fiscal_counter_currency",
    "fiscal_counter_value",
))
```
