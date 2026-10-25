"""Parsing and validation of a ZIMRA certificate and private key supplied by hand.

Never logs or returns key material in an error message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID

_CERT_RE = re.compile(
    r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.DOTALL
)
_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----.+?-----END (?:RSA |EC )?PRIVATE KEY-----",
    re.DOTALL,
)
_ENCRYPTED_KEY_RE = re.compile(r"-----BEGIN ENCRYPTED PRIVATE KEY-----")
_CSR_RE = re.compile(
    r"-----BEGIN (?:NEW )?CERTIFICATE REQUEST-----.+?-----END (?:NEW )?CERTIFICATE REQUEST-----",
    re.DOTALL,
)

MAX_PEM_CHARS = 64 * 1024


class CertBundleError(ValueError):
    """The uploaded certificate or key can't be used. The message never contains key material."""


@dataclass
class CertBundle:
    certificate_pem: str
    private_key_pem: str
    csr_pem: str = ""
    subject_cn: str = ""
    issuer_cn: str = ""
    serial_number: str = ""
    not_before: Optional[datetime] = None
    not_after: Optional[datetime] = None
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> dict:
        """Everything safe to send back to the browser. No PEM, no key."""
        return {
            "subject_cn": self.subject_cn,
            "issuer_cn": self.issuer_cn,
            "serial_number": self.serial_number,
            "valid_from": self.not_before.isoformat() if self.not_before else None,
            "valid_till": self.not_after.isoformat() if self.not_after else None,
            "warnings": list(self.warnings),
        }


def _utc(dt_naive_or_aware: datetime) -> datetime:
    if dt_naive_or_aware.tzinfo is None:
        return dt_naive_or_aware.replace(tzinfo=timezone.utc)
    return dt_naive_or_aware.astimezone(timezone.utc)


def _not_after(cert: x509.Certificate) -> datetime:
    # cryptography >= 42 exposes *_utc; older versions only return naive UTC.
    value = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
    return _utc(value)


def _not_before(cert: x509.Certificate) -> datetime:
    value = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before
    return _utc(value)


def _cn(name: x509.Name) -> str:
    attrs = name.get_attributes_for_oid(NameOID.COMMON_NAME)
    return attrs[0].value if attrs else ""


def _spki(public_key) -> bytes:
    return public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _normalise(pem: str) -> str:
    return pem.strip().replace("\r\n", "\n").replace("\r", "\n") + "\n"


def parse_certificate_bundle(
    certificate_text: str,
    private_key_text: str | None = None,
    csr_text: str | None = None,
    *,
    device_id: str | None = None,
    now: datetime | None = None,
) -> CertBundle:
    """Validate an uploaded certificate and private key.

    The certificate may be a lone cert, a chain, or a combined cert+key PEM; the leaf matching the
    key is kept. Passphrase-protected keys are rejected because the TLS client cannot supply one.
    """
    certificate_text = (certificate_text or "").strip()
    private_key_text = (private_key_text or "").strip()
    csr_text = (csr_text or "").strip()

    for label, text in (
        ("certificate", certificate_text),
        ("private key", private_key_text),
        ("CSR", csr_text),
    ):
        if len(text) > MAX_PEM_CHARS:
            raise CertBundleError(f"The {label} file is too large to be a PEM file.")

    if not certificate_text:
        raise CertBundleError("Upload the device certificate.")

    cert_blocks = _CERT_RE.findall(certificate_text)
    if not cert_blocks:
        raise CertBundleError(
            "No PEM certificate found in the certificate file. It should contain a "
            "'-----BEGIN CERTIFICATE-----' block (a .pem/.crt/.cer file in PEM format, "
            "not DER/binary)."
        )

    key_source = private_key_text or certificate_text
    if _ENCRYPTED_KEY_RE.search(key_source):
        raise CertBundleError(
            "The private key is passphrase-protected. Remove the passphrase first "
            "(e.g. `openssl pkey -in encrypted.key -out device.key`) and upload the result."
        )
    key_blocks = _KEY_RE.findall(key_source)
    if not key_blocks:
        raise CertBundleError(
            "No private key found. Upload the private key file, or use a combined PEM "
            "that contains both the certificate and the key."
        )
    if len(key_blocks) > 1:
        raise CertBundleError("More than one private key found — upload just the device's key.")

    try:
        key = serialization.load_pem_private_key(key_blocks[0].encode(), password=None)
    except TypeError:
        raise CertBundleError(
            "The private key is passphrase-protected. Remove the passphrase first and re-upload."
        ) from None
    except Exception:
        raise CertBundleError("The private key couldn't be read — is the file damaged?") from None

    key_spki = _spki(key.public_key())

    leaf: Optional[x509.Certificate] = None
    leaf_pem = ""
    for block in cert_blocks:
        try:
            candidate = x509.load_pem_x509_certificate(block.encode())
        except Exception:
            continue
        if _spki(candidate.public_key()) == key_spki:
            leaf, leaf_pem = candidate, block
            break
    if leaf is None:
        raise CertBundleError(
            "The private key doesn't match the certificate. Make sure both files are for "
            "the same device and were issued together."
        )

    current = _utc(now) if now else datetime.now(timezone.utc)
    not_after, not_before = _not_after(leaf), _not_before(leaf)
    if not_after <= current:
        raise CertBundleError(
            f"This certificate expired on {not_after:%d %b %Y}. Upload a current one "
            "(renew it with ZIMRA first)."
        )

    warnings: List[str] = []
    if not_before > current:
        warnings.append(f"This certificate isn't valid until {not_before:%d %b %Y %H:%M} UTC.")

    subject_cn = _cn(leaf.subject)
    if device_id and str(device_id).isdigit() and f"{int(device_id):010d}" not in subject_cn:
        warnings.append(
            f"The certificate's name ({subject_cn or 'none'}) doesn't contain this device ID "
            f"({int(device_id):010d}). Double-check you picked the right device."
        )

    csr_pem = ""
    if csr_text:
        csr_blocks = _CSR_RE.findall(csr_text)
        if csr_blocks:
            csr_pem = _normalise(csr_blocks[0])

    return CertBundle(
        certificate_pem=_normalise(leaf_pem),
        private_key_pem=_normalise(key_blocks[0]),
        csr_pem=csr_pem,
        subject_cn=subject_cn,
        issuer_cn=_cn(leaf.issuer),
        serial_number=format(leaf.serial_number, "X"),
        not_before=not_before,
        not_after=not_after,
        warnings=warnings,
    )


def describe_certificate(certificate_pem: str) -> Optional[dict]:
    """Subject and expiry of a stored certificate, or None if it cannot be parsed."""
    try:
        cert = x509.load_pem_x509_certificate((certificate_pem or "").encode())
        return {
            "subject_cn": _cn(cert.subject),
            "valid_till": _not_after(cert).isoformat(),
        }
    except Exception:
        return None
