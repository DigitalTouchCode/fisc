import base64
import binascii
import hashlib
from decimal import ROUND_HALF_UP, Decimal
from typing import Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from django.db import transaction
from dotenv import load_dotenv
from loguru import logger

from fiscguy.exceptions import CryptoError, DeviceNotFoundError, PersistenceError
from fiscguy.models import Certs, Device
from fiscguy.utils.cert_temp_manager import CertTempManager

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
        self._cert_manager = None
        self._private_key_path_provided = private_key_path
        self.password = password
        self._private_key = None

    @property
    def private_key_path(self):
        if self._cert_manager is None:
            c = Certs.objects.filter(device__isnull=False).first()
            if c:
                self._cert_manager = CertTempManager(c.certificate, c.certificate_key)
            elif self._private_key_path_provided:
                self._cert_manager = self._private_key_path_provided
            else:
                return None

        if isinstance(self._cert_manager, CertTempManager):
            return self._cert_manager._key_path
        return self._cert_manager

    def load_private_key(self):
        """
        Load private key from file.

        Returns:
            RSAPrivateKey: Loaded private key object
        """
        try:
            with open(self.private_key_path, "rb") as key_file:
                self._private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=self.password.encode() if self.password else None,
                    backend=default_backend(),
                )
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

    def sign_data(self, data):
        """
        Sign data using RSA private key with SHA-256.

        Args:
            data (str): Data to sign

        Returns:
            str: Base64 encoded signature
        """
        private_key = self.load_private_key()

        try:
            signature = private_key.sign(data.encode(), padding.PKCS1v15(), hashes.SHA256())

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
            signature = self.sign_data(signature_string)

            return {"hash": hash_value, "signature": signature}
        except Exception as e:
            logger.error(f"Error generating hash and signature: {e}")
            return

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
            receipt_type (str): Type of receipt (e.g., 'FiscalInvoice' or 'Creditnote')
            receipt_currency (str): Currency code (e.g., 'USD')
            receipt_global_no (int): Global receipt number
            receipt_date (str): Receipt date in ISO format
            receipt_total (Decimal): Total amount
            receipt_taxes (list): List of tax dictionaries
            previous_receipt_hash (str): Hash of previous receipt (optional)

        Returns:
            str: Signature string
        """
        receipt_total_cents = self._decimal_to_cents(receipt_total)

        def format_tax_line(tax):
            """Format a single tax line for signature"""
            if tax.get("taxPercent") is not None:
                tax_percent = f"{self._to_decimal(tax['taxPercent']).quantize(Decimal('0.01'))}"
            else:
                tax_percent = 0

            tax_amount_cents = self._decimal_to_cents(tax["taxAmount"])
            sales_amount_cents = self._decimal_to_cents(tax["salesAmountWithTax"])

            if tax.get("taxPercent") is not None:
                return f"{tax_percent}{tax_amount_cents}{sales_amount_cents}"
            return f"{tax_amount_cents}{sales_amount_cents}"

        # Sort taxes by taxID and taxCode
        sorted_taxes = sorted(receipt_taxes, key=lambda x: (x["taxID"], x.get("taxCode", "")))

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

        return signature_string

    @staticmethod
    def _to_decimal(value) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @classmethod
    def _decimal_to_cents(cls, value) -> int:
        decimal_value = cls._to_decimal(value)
        cents = (decimal_value * Decimal("100")).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
        return int(cents)

    @staticmethod
    def generate_key_and_csr(device_sn: str, device_id: int, env: bool = True) -> Tuple:
        """
        Generates a new RSA private key and a CSR, stores both in the Certs table.

        Args:
            device_sn (str): Device serial number
            device_id (int): Device ID
            env (bool): True for production, False for test

        Returns:
            tuple: (private_key_pem, csr_pem)
        """

        try:
            device = Device.objects.get(device_id=device_id)
        except Device.DoesNotExist:
            raise DeviceNotFoundError(f"Device {device_id} not found")

        existing = Certs.objects.filter(device=device, production=env).first()
        if existing and existing.csr and existing.certificate_key:
            logger.warning("CSR already exists", device_id=device_id, production=env)
            return existing.certificate_key, existing.csr

        # Generate private key
        try:
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )

            private_key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode("utf-8")

        except Exception as e:
            raise CryptoError("Failed to generate private key") from e

        # Build CSR
        try:
            common_name = f"ZIMRA-{device_sn}-{int(device_id):010d}"

            csr = (
                x509.CertificateSigningRequestBuilder()
                .subject_name(
                    x509.Name(
                        [
                            x509.NameAttribute(NameOID.COUNTRY_NAME, "ZW"),
                            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Zimbabwe"),
                            x509.NameAttribute(NameOID.LOCALITY_NAME, "Harare"),
                            x509.NameAttribute(
                                NameOID.ORGANIZATION_NAME, "Zimbabwe Revenue Authority"
                            ),
                            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "FDMS"),
                            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                        ]
                    )
                )
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName(common_name)]),
                    critical=False,
                )
                .sign(private_key, hashes.SHA256(), default_backend())
            )

            csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")

        except Exception as e:
            raise CryptoError("Failed to generate CSR") from e

        # Save to DB
        try:
            with transaction.atomic():
                cert_record, _ = Certs.objects.get_or_create(
                    device=device,
                )
                cert_record.certificate_key = private_key_pem
                cert_record.csr = csr_pem
                cert_record.save()

                logger.info(f"Created cert obj: {cert_record.device}")

        except Exception as e:
            raise PersistenceError("Failed to save certificate data") from e

        logger.info("Generated CSR and private key", device_id=device_id, production=env)

        return private_key_pem, csr_pem
