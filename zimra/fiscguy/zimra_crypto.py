"""
Cryptographic Utilities for ZIMRA Receipt Signing
Handles hashing, signing, and verification code generation.
"""

import base64
import binascii
import hashlib
import os

import OpenSSL.crypto as crypto
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import NameOID
from dotenv import load_dotenv
from loguru import logger

from fiscguy.models import Certs

load_dotenv()


class ZIMRACrypto:
    """
    Handles all cryptographic operations for ZIMRA receipt signing.
    """

    def __init__(self, private_key_path=None, password=None):
        """
        Initialize crypto utilities.

        Args:
            private_key_path (str): Path to private key file
            password (str): Password for private key (if encrypted)
        """
        self.private_key_path = private_key_path or os.getenv(
            "DEVICE_PRIVATE_KEY_PATH", "device_private_key.pem"
        )
        self.password = password
        self._private_key = None

    def load_private_key(self):
        """
        Load private key from file.

        Returns:
            RSAPrivateKey: Loaded private key object
        """
        if self._private_key:
            return self._private_key

        try:
            with open(self.private_key_path, "rb") as key_file:
                self._private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=self.password.encode() if self.password else None,
                    backend=default_backend(),
                )
            logger.info(f"Private key loaded from {self.private_key_path}")
            return self._private_key
        except FileNotFoundError:
            logger.error(f"Private key file not found at {self.private_key_path}")
            raise
        except Exception as e:
            logger.error(f"Error loading private key: {e}")
            raise

    @staticmethod
    def get_hash(data):
        """
        Generate SHA-256 hash of input data and encode as base64.

        Args:
            data (str): Data to hash

        Returns:
            str: Base64 encoded hash
        """
        hash_obj = hashlib.sha256(data.encode())
        return base64.b64encode(hash_obj.digest()).decode()

    def sign_data(self, data, private_key=None):
        """
        Sign data using RSA private key with SHA-256.

        Args:
            data (str): Data to sign
            private_key: Private key object (optional, will load if not provided)

        Returns:
            str: Base64 encoded signature
        """
        if private_key is None:
            private_key = self.load_private_key()

        try:
            signature = private_key.sign(
                data.encode(), padding.PKCS1v15(), hashes.SHA256()
            )

            return base64.b64encode(signature).decode()
        except Exception as e:
            logger.error(f"Signing Error: {e}")
            raise

    def generate_receipt_hash_and_signature(self, signature_string):
        """
        Generate both hash and signature for a receipt.

        Args:
            signature_string (str): The receipt signature string

        Returns:
            dict: Dictionary with 'hash' and 'signature' keys
        """
        try:
            hash_value = self.get_hash(signature_string)
            logger.info(f"Generated hash: {hash_value}")

            signature = self.sign_data(signature_string)
            logger.info(f"Generated signature: {signature}")

            return {"hash": hash_value, "signature": signature}
        except Exception as e:
            logger.error(f"Error generating hash and signature: {e}")
            raise

    @staticmethod
    def generate_verification_code(base64_signature):
        """
        Generate verification code from base64 signature for QR code.

        Args:
            base64_signature (str): Base64 encoded signature

        Returns:
            str: 16-character verification code in uppercase
        """
        try:
            # Decode base64 signature
            decoded_bytes = base64.b64decode(base64_signature)
            hex_string = decoded_bytes.hex()

            # Generate MD5 hash
            md5 = hashlib.md5()
            md5.update(binascii.unhexlify(hex_string))
            md5_hash = md5.hexdigest()

            # Take first 16 characters
            verification_code = md5_hash[:16]

            return verification_code.upper()
        except Exception as e:
            logger.error(f"Error generating verification code: {e}")
            raise

    def generate_receipt_signature_string(
        self,
        device_id,
        receipt_type,
        receipt_currency,
        receipt_global_no,
        receipt_date,
        receipt_total,
        receipt_taxes,
        previous_receipt_hash=None,
    ):
        """
        Generate the signature string for a receipt.

        Args:
            device_id (str): Device ID
            receipt_type (str): Type of receipt (e.g., 'FiscalInvoice')
            receipt_currency (str): Currency code (e.g., 'USD')
            receipt_global_no (int): Global receipt number
            receipt_date (str): Receipt date in ISO format
            receipt_total (Decimal): Total amount
            receipt_taxes (list): List of tax dictionaries
            previous_receipt_hash (str): Hash of previous receipt (optional)

        Returns:
            str: Signature string
        """
        # Convert total to cents
        receipt_total_cents = int(receipt_total * 100)

        def format_tax_line(tax):
            """Format a single tax line for signature"""
            if tax.get("taxPercent") is not None:
                if isinstance(tax["taxPercent"], int):
                    tax_percent = f"{tax['taxPercent']}.00"
                else:
                    tax_percent = f"{tax['taxPercent']:.2f}"
            else:
                tax_percent = ""

            tax_amount_cents = int(tax["taxAmount"] * 100)
            sales_amount_cents = int(tax["salesAmountWithTax"] * 100)

            return f"{tax.get('taxCode')}{tax_percent}{tax_amount_cents}{sales_amount_cents}"

        # Sort taxes by taxID and taxCode
        sorted_taxes = sorted(
            receipt_taxes, key=lambda x: (x["taxID"], x.get("taxCode", ""))
        )

        # Concatenate all tax lines
        tax_string = "".join(format_tax_line(tax) for tax in sorted_taxes)

        # Build signature components
        signature_components = [
            str(device_id),
            receipt_type.upper(),
            receipt_currency.upper(),
            str(receipt_global_no),
            receipt_date,
            str(receipt_total_cents),
            tax_string,
        ]

        # Add previous receipt hash if provided
        if previous_receipt_hash:
            signature_components.append(previous_receipt_hash)

        signature_string = "".join(signature_components)
        logger.info(f"Generated signature string: {signature_string}")

        return signature_string

    @staticmethod
    def generate_key_and_csr(device_sn: str, device_id: int, env: bool = True):
        """
        Generates a new RSA private key and a CSR, stores both in the Certs table.

        Args:
            device_sn (str): Device serial number
            device_id (int): Device ID
            env (bool): True for production, False for test

        Returns:
            tuple: (private_key_pem, csr_pem)
        """
        # ---- validate or create Cert record ----
        cert_record, created = Certs.objects.get_or_create(production=env)

        if cert_record.certificate_key and cert_record.csr:
            logger.info("Private key and CSR already exist – reusing them")
            return cert_record.certificate_key, cert_record.csr

        # ---- generate 2048-bit RSA key ----
        keypair = crypto.PKey()
        keypair.generate_key(crypto.TYPE_RSA, 2048)
        private_key_pem = crypto.dump_privatekey(crypto.FILETYPE_PEM, keypair).decode(
            "utf-8"
        )

        # ---- build CSR ----
        common_name = f"ZIMRA-{device_sn}-{int(device_id):010d}"

        csr_request = crypto.X509Req()
        subject = csr_request.get_subject()

        # Subject fields (ZIMRA style)
        subject.C = "ZW"
        subject.ST = "Zimbabwe"
        subject.L = "Harare"
        subject.O = "Zimbabwe Revenue Authority"
        subject.OU = "FDMS"
        subject.CN = common_name

        # Add SAN (optional, here CN only)
        csr_request.add_extensions(
            [
                crypto.X509Extension(
                    b"subjectAltName", False, f"DNS:{common_name}".encode("utf-8")
                )
            ]
        )

        csr_request.set_pubkey(keypair)
        csr_request.sign(keypair, "sha256")

        csr_pem = crypto.dump_certificate_request(
            crypto.FILETYPE_PEM, csr_request
        ).decode("utf-8")

        # ---- save to DB ----
        cert_record.certificate_key = private_key_pem
        cert_record.csr = csr_pem
        cert_record.save()

        logger.info(
            f"Generated new RSA private key and CSR for {'production' if env else 'test'} environment"
        )

        return private_key_pem, csr_pem


# Convenience function for backward compatibility
def run(signature_string):
    """
    Process input: hash and sign it.
    This function maintains backward compatibility with existing code.

    Args:
        signature_string (str): The signature string to process

    Returns:
        dict: Dictionary with 'hash' and 'signature' keys
    """
    crypto = ZIMRACrypto()
    return crypto.generate_receipt_hash_and_signature(signature_string)
