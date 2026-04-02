class FiscalisationError(Exception):
    """Base exception for all fiscalisation-related errors."""

    pass


class CertNotFoundError(FiscalisationError):
    """Raised when a required certificate cannot be found."""

    pass


class CryptoError(FiscalisationError):
    """Raised when a cryptographic operation fails."""

    pass


class PersistenceError(FiscalisationError):
    """Raised when a database persistence operation fails."""

    pass


class RegistrationError(FiscalisationError):
    """Raised when a general registration process fails."""

    pass


class DeviceNotFoundError(FiscalisationError):
    """Raised when a requested device cannot be found."""

    pass


class TenantNotFoundError(FiscalisationError):
    """Raised when a tenant cannot be found."""

    pass


class ZIMRAAPIError(FiscalisationError):
    """Raised when a ZIMRA API request fails or returns an error."""

    pass


class ValidationError(FiscalisationError):
    """Raised when input data fails validation checks."""

    pass


class AuthenticationError(FiscalisationError):
    """Raised when authentication fails or credentials are invalid."""

    pass


class ConfigurationError(FiscalisationError):
    """Raised when required configuration is missing or invalid."""

    pass


class TaxError(FiscalisationError):
    """Raised when tax-related operations fail."""

    pass


class FiscalDayError(FiscalisationError):
    """Raised when opening a fiscal day fails."""

    pass


class ReceiptSubmissionError(FiscalisationError):
    """Raised when submission of a receipt fails."""

    pass


class DeviceRegistrationError(FiscalisationError):
    """Raised when device registration fails."""

    pass


class CertificateError(FiscalisationError):
    """Raised when there is a certificate-related error."""

    pass


class StatusError(FiscalisationError):
    """Raised when an invalid or unexpected status is encountered."""

    pass


class DevicePingError(FiscalisationError):
    """Raised when a device ping or connectivity check fails."""

    pass


class ZIMRAClientError(FiscalisationError):
    """Raised when the ZIMRA client encounters an internal error."""

    pass


class CloseDayError(FiscalisationError):
    """Raised when closing a fiscal day fails."""

    pass
