"""
ZIMRA Fiscal Device Library

Public API for fiscal device operations. Import functions directly:

    from fiscguy import open_day, close_day, submit_receipt, get_status, get_taxes, get_configuration

Each function handles initialization and error handling transparently.
"""

default_app_config = "fiscguy.apps.FiscguyConfig"


def __getattr__(name):
    """Lazy-load API functions on first access."""
    if name in (
        "open_day",
        "close_day",
        "get_status",
        "submit_receipt",
        "get_configuration",
        "get_taxes",
    ):
        from fiscguy import api

        return getattr(api, name)
    raise AttributeError(f"module 'fiscguy' has no attribute '{name}'")


__all__ = [
    "open_day",
    "close_day",
    "get_status",
    "submit_receipt",
    "get_configuration",
    "get_taxes",
]
