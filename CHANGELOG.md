# Changelog

All notable changes to Fiscguy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

### Deprecated

### Removed

### Security

## [0.1.0] - 2026-02-08

### Added

- Initial public release of Fiscguy library
- **Core API Functions:**
  - `open_day()` - Open a new fiscal day
  - `close_day()` - Close the current fiscal day
  - `submit_receipt()` - Create and submit receipts
  - `get_status()` - Get device and fiscal status
  - `get_configuration()` - Fetch device configuration
  - `get_taxes()` - Fetch available tax types

- **Service Layer:**
  - `ReceiptService` - Receipt creation and submission
  - `ClosingDayService` - Fiscal day closing logic
  - Support for fiscal invoices and credit notes

- **ZIMRA Integration:**
  - `ZIMRAClient` - FDMS HTTP client with certificate auth
  - `ZIMRAReceiptHandler` - Receipt formatting and signing
  - `ZIMRACrypto` - Cryptographic operations (hashing, signing)

- **Models:**
  - Device, FiscalDay, FiscalCounter, Receipt, ReceiptLine
  - Taxes, Configuration, Certs, Buyer

- **Serializers:**
  - `ReceiptCreateSerializer` - Receipt creation with tax_name resolution
  - `ReceiptLineCreateSerializer` - Line items with dynamic tax lookup
  - `ConfigurationSerializer`, `TaxesSerializer`

- **Management Commands:**
  - `init_device` - Interactive device registration and configuration

- **Testing:**
  - 22+ comprehensive unit tests
  - APILibraryTestSetup fixture with full test data
  - Mocked ZIMRA/crypto/file I/O operations
  - 90%+ code coverage

- **Documentation:**
  - README.md with quick start and API reference
  - CONTRIBUTING.md for developers
  - Docstrings throughout codebase
  - Inline comments for complex logic

- **Configuration:**
  - pyproject.toml with PEP 517 build system
  - setup.py for setuptools compatibility
  - MANIFEST.in for package distribution
  - requirements.txt and requirements-dev.txt

- **Lazy Loading:**
  - Module-level caching via `__getattr__` in `__init__.py`
  - Prevents circular imports during Django startup
  - Device, Client, Handler cached after first use

### Changed

- Refactored Django REST API views to thin wrappers
  - Views now call library functions from `fiscguy.api`
  - Eliminates code duplication
  - Improves testability

- Modularized business logic into services
  - Separated concerns (receipt, closing day)
  - Easy to compose and extend

### Fixed

- Fixed recursive `submit_receipt()` call in `ZIMRAReceiptHandler`
- Removed early return in `ZIMRAClient.submit_receipt()` preventing HTTP POST
- Fixed circular imports by implementing lazy loading
- Resolved tax_name serialization by creating `ReceiptLineCreateSerializer`
- Fixed read-only serializer blocking nested writes

### Security

- Certificate-based HTTPS authentication with ZIMRA FDMS
- Private keys never persisted to disk (PEM file lifecycle management)
- Input validation on all API functions
- Type hints for runtime safety

---

## [Unreleased] Features in Progress

These features are planned for future releases:

- [ ] GraphQL API support
- [ ] Async/await support
- [ ] Multi-device management
- [ ] Receipt templates
- [ ] Webhook notifications
- [ ] Admin dashboard
- [ ] Batch operations
- [ ] Offline mode with sync
- [ ] Audit logging
- [ ] Performance optimizations

---

## How to Read This Changelog

- **Added** for new features
- **Changed** for changes in existing functionality
- **Deprecated** for soon-to-be removed features
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** in case of vulnerabilities

---

## Versioning

Fiscguy follows [Semantic Versioning](https://semver.org/):

- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible new features
- **PATCH** version for backwards-compatible bug fixes

Example: `0.1.0` = Major.Minor.Patch
