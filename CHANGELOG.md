# Changelog

All notable changes to Fiscguy are documented in this file.  
Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

### Changed

### Fixed

### Deprecated

### Removed

### Security

## [0.1.2] - 2026-02-09

### Fixed

- Added missing pyOpenssl dependency.
- Minor packaging and build improvements for consistency and compatibility.

## [0.1.1] - 2026-02-08

### Added

- **Initial public release** of Fiscguy library.
- **Core API Functions:**
  - `open_day()`, `close_day()`, `submit_receipt()`, `get_status()`, `get_configuration()`, `get_taxes()`
- **Service Layer:** `ReceiptService`, `ClosingDayService`
- **ZIMRA Integration:** `ZIMRAClient`, `ZIMRAReceiptHandler`, `ZIMRACrypto`
- **Models & Serializers:** Device, FiscalDay, FiscalCounter, Receipt, ReceiptLine, ConfigurationSerializer, TaxesSerializer, ReceiptLineCreateSerializer
- **Management Commands:** `init_device`
- **Testing:** 22+ unit tests, mocked ZIMRA/crypto/file I/O, 90%+ coverage
- **Documentation & Configuration:** README.md, CONTRIBUTING.md, pyproject.toml, setup.py, MANIFEST.in
- **Lazy Loading:** Prevents circular imports; caches device, client, handler after first use.
