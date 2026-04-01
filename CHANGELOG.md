# Changelog

All notable changes to Fiscguy are documented in this file.  
Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Semantic Versioning](https://semver.org/).

## [Unreleased 0.1.6]

### Added
- Receipt global numbers are now sourced from FDMS (`lastReceiptGlobalNo + 1`) and persisted
  locally. If the local value differs from FDMS, a warning is logged and FDMS is used as the
  source of truth.
- Fiscal day opening service now persists `lastFiscalDayNo + 1` from FDMS, keeping the local
  database in sync with FDMS at all times.
- Cursor-based pagination for receipt listing endpoint (`GET /api/receipts/`). Supports
  configurable page sizes via `?page_size=N` parameter (max 100 items).
- Receipt lines are now included in paginated receipt list responses via `prefetch_related()`.

### Changed
- Monetary fields in models now use `DecimalField` instead of `FloatField` for precise financial
  calculations:
  - `Taxes.percent`: `DecimalField(max_digits=5, decimal_places=2)`
  - `Receipt.total_amount`: `DecimalField(max_digits=12, decimal_places=2)`
  - `ReceiptLine.quantity`, `unit_price`, `line_total`, `tax_amount`: `DecimalField` with appropriate precision
- Receipt submission now uses database transactions to ensure atomic operations: if any error occurs
  during submission (processing, signing, or FDMS submission), the receipt is rolled back and NOT
  recorded in the database.

### Fixed
- `OpenDayView`, `CloseDayView` and `DevicePing` now correctly use `POST` instead of `GET`, as both endpoints
  perform state-changing operations.
- `ClosingDayService`: fiscal day date in the closing hash string now uses the date the fiscal
  day was opened (`fiscal_day.created_at`) instead of today's date, matching what FDMS holds
  on record.
- `ClosingDayService`: byTax counters are now sorted by `(currency ASC, taxID ASC)` before
  concatenation, matching the required ordering in spec section 13.3.1.
- `ClosingDayService`: zero-value counters are now excluded from all builders. Previously
  `SaleByTax` and `CreditNoteByTax` had no zero filter, violating the spec rule that zero-value
  counters must not be submitted.
- `ClosingDayService`: `_money_value` now uses `int(round(value * 100))` instead of
  `int(value * 100)` to prevent floating point truncation (e.g. `699.75 * 100 = 69974.99`
  becoming `69974` instead of `69975`).
- `ZIMRAReceiptHandler`: `CreditNoteByTax` counter now correctly uses `sales_amount_with_tax`
  per tax group instead of `receipt_data["receiptTotal"]`. Previously the full receipt total
  was written once per tax group, inflating the counter and causing `CountersMismatch` on
  close day.
- `Update fiscal counter`. prevents race condition by using F for row level db locking.

### Removed
- Removed deprecated `pyOpenSSL` (`OpenSSL.crypto`) usage from `ZIMRACrypto.generate_key_and_csr`
  and replaced it with the `cryptography` library, which was already a project dependency.
- `api.py` it had a module level caching which was causing a memory leak.
- `ClosingDayService`: removed unused `_today()` method and its `date_today` import after
  the closing string was corrected to use `fiscal_day.created_at` directly.

## 0.1.5 - 2026-03-16

### Added
- Buyer feature CRUD via endpoint and via API (users can now attach buyer data on receipt payload)
- ZIMRA ping method: report that the device is online
- flake8 configuration
- Multiple payment methods

### Changed
- Internal structure of `ping_device`
- receipt number to match ZIMRA receiot global number.

### Fixed
- Redundant imports removed from `init_device.py`

### Deprecated
- None

### Removed
- Redundant imports from `init_device.py`

## [0.1.4] - 2026-02-09

### Fixed
- Pinned `cryptography` dependency to a wheel-supported version to prevent Rust build failures on Termux, Android, and minimal Linux environments
- Improved installation reliability across platforms (CI, Docker, mobile, and desktop)

### Changed
- Minor packaging and dependency resolution improvements

## [0.1.3] - 2026-02-09

### Fixed
- Added missing `pyOpenSSL` dependency
- Minor packaging and build improvements for consistency and compatibility

## [0.1.2] - 2026-02-08

### Added
- **Initial public release** of Fiscguy library
- **Core API Functions:** `open_day()`, `close_day()`, `submit_receipt()`, `get_status()`, `get_configuration()`, `get_taxes()`
- **Service Layer:** `ReceiptService`, `ClosingDayService`
- **ZIMRA Integration:** `ZIMRAClient`, `ZIMRAReceiptHandler`, `ZIMRACrypto`
- **Models & Serializers:** Device, FiscalDay, FiscalCounter, Receipt, ReceiptLine, ConfigurationSerializer, TaxesSerializer, ReceiptLineCreateSerializer
- **Management Commands:** `init_device`
- **Testing:** 22+ unit tests, mocked ZIMRA/crypto/file I/O, 90%+ coverage
- **Documentation & Configuration:** README.md, CONTRIBUTING.md, pyproject.toml, setup.py, MANIFEST.in
- **Lazy Loading:** Prevents circular imports; caches device, client, handler after first use
