import pytest

from fiscguy.exceptions import CryptoError
from fiscguy.services.configuration_service import ConfigurationService
from fiscguy.zimra_base import zimra_proxies
from fiscguy.zimra_crypto import ZIMRACrypto


def test_standard_tax_is_picked_by_name_not_id():
    taxes = [
        {"taxID": 1, "taxName": "Exempt", "taxPercent": 0},
        {"taxID": 515, "taxName": "Standard rated 15.5%", "taxPercent": 15.5},
    ]
    assert ConfigurationService._standard_tax_index(taxes) == 1


def test_standard_tax_falls_back_to_highest_non_withholding_rate():
    taxes = [
        {"taxID": 1, "taxName": "Exempt", "taxPercent": 0},
        {"taxID": 2, "taxName": "Withholding", "taxPercent": 10},
        {"taxID": 3, "taxName": "VAT", "taxPercent": 15},
    ]
    assert ConfigurationService._standard_tax_index(taxes) == 2


def test_standard_tax_none_when_nothing_plausible():
    assert ConfigurationService._standard_tax_index([{"taxID": 1, "taxName": "Exempt"}]) is None


def test_crypto_without_device_or_key_path_refuses_to_sign():
    with pytest.raises(CryptoError):
        ZIMRACrypto().private_key_path


def test_zimra_proxy_is_opt_in(monkeypatch):
    monkeypatch.delenv("ZIMRA_PROXY", raising=False)
    assert zimra_proxies() is None
    monkeypatch.setenv("ZIMRA_PROXY", "http://proxy.local:8889")
    assert zimra_proxies() == {"http": "http://proxy.local:8889", "https": "http://proxy.local:8889"}
