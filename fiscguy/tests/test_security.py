from pathlib import Path

import pytest
from django.db import connection

from fiscguy.models import Certs, Device
from fiscguy.utils.cert_temp_manager import CertTempManager


@pytest.fixture
def device(db):
    return Device.objects.create(
        org_name="Test Org",
        activation_key="test-key-123",
        device_id="TEST-DEVICE-001",
        device_model_name="ModelX",
        device_model_version="1.0",
        device_serial_number="SN-12345",
        production=False,
    )


@pytest.mark.django_db
def test_certificate_key_is_encrypted_at_rest(device):
    private_key = "-----BEGIN PRIVATE KEY-----\ntest-key\n-----END PRIVATE KEY-----"
    cert = Certs.objects.create(
        device=device,
        csr="csr",
        certificate="certificate",
        certificate_key=private_key,
        production=False,
    )

    cert.refresh_from_db()
    assert cert.certificate_key == private_key

    with connection.cursor() as cursor:
        cursor.execute("SELECT certificate_key FROM fiscguy_certs WHERE id = %s", [cert.id])
        stored_value = cursor.fetchone()[0]

    assert stored_value != private_key
    assert stored_value.startswith("fernet$")


def test_cert_temp_manager_cleans_up_temp_files():
    manager = CertTempManager("CERTIFICATE", "PRIVATE KEY")
    pem_path = Path(manager.cert_path)
    key_path = Path(manager.key_path)
    temp_dir = pem_path.parent

    assert pem_path.exists()
    assert key_path.exists()

    manager.close()

    assert not temp_dir.exists()
