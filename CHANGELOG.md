# Changelog

All notable changes to Fiscguy are documented in this file.  
Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Semantic Versioning](https://semver.org/).

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
