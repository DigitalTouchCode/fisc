import shutil
import tempfile
import threading
from pathlib import Path


class CertTempManager:
    """
    Manages the life cycle of client TLS certificates loaded from DB.
    Thread-safe and reusable accross FDMS requests
    """

    def __init__(self, cert_pem: str, key_pem: str):
        self._lock = threading.Lock()
        self._temp_dir = Path(tempfile.mkdtemp(prefix="zimra_dms_"))
        self._pem_path = self._temp_dir / "client.pem"
        self._key_path = self._temp_dir / "key.pem"

        self._pem_path.write_text(f"{cert_pem}\{key_pem}")
        self._key_path.write_text(f"{key_pem}")
        self._closed = False

        @property
        def cert_path(self) -> str:
            return str(self._pem_path)
        
        @property
        def key_path(self) -> str:
            return str(self._key_path)

        def close(self):
            with self._lock:
                if not self._closed:
                    shutil.rmtree(self._temp_dir, ignore_errors=True)
                    self._closed = True

        def __del__(self):
            self.close()
