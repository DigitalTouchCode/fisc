class FiscalisationError(Exception):
    """Base exception for all fiscalisation service errors."""

    pass


class CertNotFoundError(FiscalisationError):
    """Raised when a certificate is not found."""

    pass


class CryptoError(FiscalisationError):
    """Raised when cryptographic operations fail."""

    pass


class PersistenceError(FiscalisationError):
    """Raised when database persistence operations fail."""

    pass


class RegistrationError(FiscalisationError):
    """Raised when device registration fails."""

    pass


class DeviceNotFoundError(FiscalisationError):
    """Raised when a device is not found."""

    pass


class TenantNotFoundError(FiscalisationError):
    """Raised when a tenant is not found."""

    pass


class ZIMRAAPIError(FiscalisationError):
    """Raised when ZIMRA API calls fail."""

    pass


class ValidationError(FiscalisationError):
    """Raised when data validation fails."""

    pass


class AuthenticationError(FiscalisationError):
    """Raised when authentication fails."""

    pass


class ConfigurationError(FiscalisationError):
    """Raised when configuration is invalid or missing."""

    pass


class TaxError(FiscalisationError):
    """Raised when tax crud operations fail."""

    pass


class FiscalDayError(FiscalisationError):
    """Raised when fiscal day opening fails"""

    pass


class ReceiptSubmissionError(FiscalisationError):
    """Rasied when a receipt submission fails"""

    pass


class DeviceRegistrationError(FiscalisationError):
    """Raised when device registration fails"""

    pass


class CertificateError(FiscalisationError):
    """Raised when they is a cerificate error"""

    pass


class StatusError(FiscalisationError):
    pass


class DevicePingError(FiscalisationError):
    pass


class ZIMRAClientError(FiscalisationError):
    pass


class CloseDayError(FiscalisationError):
    pass


class CertificateError(FiscalisationError):
    pass
