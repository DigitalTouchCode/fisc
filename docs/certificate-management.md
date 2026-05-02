# Certificate Management

FiscGuy uses mutual TLS authentication with ZIMRA FDMS. The device must hold a valid certificate issued by ZIMRA to submit any signed request.

---

## How Certificates Work

1. `init_device` generates an RSA key pair and a Certificate Signing Request (CSR)
2. For initial onboarding, the CSR is sent to ZIMRA FDMS `registerDevice`
3. ZIMRA returns a signed certificate
4. The certificate and private key are stored in the `Certs` model
5. Every request to FDMS uses the certificate for mutual TLS authentication

---

## Certificate Storage

Certificates are stored in the `Certs` model:

```python
from fiscguy.models import Certs

cert = Certs.objects.first()
print(cert.certificate)      # PEM-encoded certificate
print(cert.certificate_key)  # PEM-encoded private key
print(cert.csr)              # Original CSR
print(cert.production)       # True = production, False = testing
```

At runtime, `ZIMRAClient` writes the certificate and key to a temporary PEM file used by the `requests` session. The temp file is cleaned up when the client is closed.

---

## Certificate Renewal

Certificates expire. When they do, all signed requests will fail with `BadCertificateSignature` or an authentication error.

### Via REST endpoint

```
POST /fiscguy/issue-certificate/
```

Response on success:
```json
{"message": "Certificate issued successfully"}
```

### Via Python

```python
from fiscguy.services.certs_service import CertificateService
from fiscguy.models import Device

device = Device.objects.first()
CertificateService(device).issue_certificate()
```

### Raises

| Exception | Cause |
|-----------|-------|
| `CertificateError` | FDMS rejected the renewal request |
| `Exception` | Unexpected error during renewal |

---

## Key Generation

FiscGuy supports two key algorithms as per ZIMRA spec section 12:

| Algorithm | Spec reference |
|-----------|----------------|
| RSA 2048 | Section 12.1.2 |
| ECC ECDSA secp256r1 (P-256) | Section 12.1.1 |

The `cryptography` library is used for all key generation and signing. `pyOpenSSL` is no longer used.

---

## Security Notes

- The private key never leaves the device. Only the CSR is sent to ZIMRA.
- Do not commit `Certs` data to version control.
- In production, consider encrypting `Certs.certificate` and `Certs.certificate_key` at rest using a library like `cryptography.fernet`. See the project roadmap for planned support.
- The temporary PEM file is written to a `tempfile.mkdtemp()` directory and deleted when `ZIMRAClient.close()` is called.

---

## Checking Certificate Status

```python
from fiscguy import get_status

status = get_status()
# Check for certificate-related errors in the response
print(status)
```

If the certificate is expired or invalid, `get_status()` will raise `StatusError` with an authentication error from FDMS.
