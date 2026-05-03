# Changelog

All notable changes to Fiscguy are documented in this file.  
Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Semantic Versioning](https://semver.org/).

## [0.1.8] - 2026-05-03

### Added
- Close-day lifecycle state tracking with local `open`, `close_pending`, `close_failed`,
  and `closed` states alongside FDMS status reconciliation.
- Background close-day polling when FDMS returns `FiscalDayCloseInitiated`, allowing the
  request thread to return immediately while final close status is resolved asynchronously.
- Regression tests covering close-day pending flow, background polling completion, encrypted
  certificate-key storage, and temporary certificate cleanup.

### Changed
- README documentation was updated to reflect the current close-day flow, security posture,
  dependency-audit guidance, and current sample data.
- Installation, receipt-type, and fiscal-counter examples were aligned to use `Cas Bz`
  and the 5-digit sample device ID `41872`.
- Dependency baselines were raised to patched versions after a vulnerability audit,
  including Django, cryptography, Pillow, Pygments, and pytest.

### Fixed
- Certificate private keys are now encrypted at rest instead of being stored as plaintext
  in the `Certs` table.
- Django admin no longer exposes raw certificate and private-key fields by default.
- `CertTempManager` now correctly defines cleanup methods, applies restrictive file
  permissions, and reliably removes temporary PEM material after use.
- Documentation coherence issues were cleaned up across `README.md`, `docs/index.md`,
  and related setup/reference pages.

### Security
- Ran a dependency vulnerability audit with `pip-audit` and updated vulnerable packages
  to fixed versions. The updated dependency manifest reports no known vulnerabilities.

## 0.1.6 / 0.1.7
### Added
- **ARCHITECTURE.md** - Comprehensive internal engineering documentation covering:
  - Layered architecture and component responsibilities
  - Complete data model documentation with relationships and constraints
  - Service layer details (ReceiptService, OpenDayService, ClosingDayService, etc.)
  - Cryptography & security implementation (RSA signing, SHA-256 hashing)
  - ZIMRA integration details and API payload specifications
  - Receipt processing pipeline with flow diagrams
  - Fiscal day management and counter tracking
  - Database design with indexes and relationships
  - Development guidelines for contributors
- **USER_GUIDE.md** - General user and integration documentation including:
  - Feature overview and installation instructions
  - Quick start guide with 5-step setup
  - Complete API endpoint reference with examples
  - 4 practical usage examples (cash receipt, buyer, credit note, Django integration)
  - Conceptual explanations (fiscal devices, fiscal days, receipt types, counters)
  - Comprehensive troubleshooting guide for common issues
  - FAQ covering 15+ frequently asked questions
- Receipt global numbers are now sourced from FDMS (`lastReceiptGlobalNo + 1`) and persisted
  locally. If the local value differs from FDMS, a warning is logged and FDMS is used as the
  source of truth.
- Fiscal day opening service now persists `lastFiscalDayNo + 1` from FDMS, keeping the local
  database in sync with FDMS at all times.
- Cursor-based pagination for receipt listing endpoint (`GET /api/receipts/`). Supports
  configurable page sizes via `?page_size=N` parameter (max 100 items).
- Receipt lines are now included in paginated receipt list responses via `prefetch_related()`.
- Certificate renewal endpoint (`IssueCertificateView`) - POST endpoint to issue/renew
  device certificates using the `CertificateService.issue_certificate()` flow. Returns
  success or detailed error responses when certificate issuance fails.
- Debit note support across validation, receipt payload generation, fiscal counter updates,
  and close-day payload construction.
- Additional FDMS configuration metadata persistence:
  `deviceOperatingMode`, `taxPayerDayMaxHrs`, `taxpayerDayEndNotificationHrs`,
  and `certificateValidTill`.
- Debit-note regression tests covering serializer validation, FDMS payload mapping,
  and debit-note counter creation.

### Changed
- Monetary fields in models now use `DecimalField` instead of `FloatField` for precise financial
  calculations:
  - `Taxes.percent`: `DecimalField(max_digits=5, decimal_places=2)`
  - `Receipt.total_amount`: `DecimalField(max_digits=12, decimal_places=2)`
  - `ReceiptLine.quantity`, `unit_price`, `line_total`, `tax_amount`: `DecimalField` with appropriate precision
- Receipt submission now uses database transactions to ensure atomic operations: if any error occurs
  during submission (processing, signing, or FDMS submission), the receipt is rolled back and NOT
  recorded in the database.
- ZIMRA FDMS client and bootstrap flow aligned to the current gateway contract:
  header names now use `DeviceModelName` and `DeviceModelVersion`, and device/public
  endpoint paths now use the current lower-camel FDMS paths such as `registerDevice`,
  `submitReceipt`, and `closeDay`.
- Receipt payloads now map internal receipt types to FDMS wire values
  `FiscalInvoice`, `CreditNote`, and `DebitNote`.
- QR code generation now prefers the `qrUrl` returned by `getConfig` instead of always
  hardcoding the FDMS API host.
- Certificate renewal now uses `issueCertificate` semantics instead of reusing
  the initial registration flow.
- Documentation examples and links were aligned with the current repo layout and
  naming, including `Cas Bz` sample data and direct links to local markdown docs.
- Installation, receipt-type, and fiscal-counter examples were refreshed to use
  the current sample organisation (`Cas Bz`) and a 5-digit sample device ID (`41872`).

### Fixed
- `ReceiptCreateSerializer`: added `device` field to serializer's `fields` list so that the device
  relation is properly saved when creating receipts. Previously, the device ID passed from
  `ReceiptService` was being ignored during validation, resulting in receipts being created
  without an associated device.
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
- `ZIMRAReceiptHandler`: previous-receipt hash lookup is now scoped to the current device and
  safely handles the first receipt in a fiscal chain.
- `ZIMRAReceiptHandler`: fiscal counter updates are now scoped to the current device and use
  canonical counter names/currency casing, preventing cross-device leakage and mismatched
  close-day payload entries.
- `init_device`: certificate persistence now stores the actual CSR, private key, certificate,
  and environment on the device certificate record instead of updating certificate text only.
- Documentation coherence issues were cleaned up in `README.md` and `docs/index.md`,
  including stale local links, outdated troubleshooting text, and example inconsistencies.

### Removed
- Removed deprecated `pyOpenSSL` (`OpenSSL.crypto`) usage from `ZIMRACrypto.generate_key_and_csr`
  and replaced it with the `cryptography` library, which was already a project dependency.
- `api.py` it had a module level caching which was causing a memory leak.
- `ClosingDayService`: removed unused `_today()` method and its `date_today` import after
  the closing string was corrected to use `fiscal_day.created_at` directly.
- Stale documentation claims that receipts are queued and auto-synced while FDMS is offline.
  The current implementation documents the actual supported mode: direct online `submitReceipt`.

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
