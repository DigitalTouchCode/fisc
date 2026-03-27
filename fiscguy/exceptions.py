"""base file for fiscguy excecptions"""


class FiscalisationError(Exception):
    """base exception class"""

    pass


class FiscalDayError(FiscalisationError):
    """Raised when open fiscal day fails"""

    pass


class ReceiptSubmissionError(FiscalisationError):
    """Raised when receipt submission fails"""

    pass
