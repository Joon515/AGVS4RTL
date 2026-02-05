"""Config storage with hybrid encryption for API keys.

Uses RSA-OAEP + AES-GCM for secure key storage.
Note: This is a practical implementation. For true post-quantum security,
replace RSA with a PQC KEM (e.g., Kyber) when stable libraries are available.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.backends import default_backend
except ImportError as exc:  # pragma: no cover - environment setup
    raise RuntimeError(
        "Missing cryptography dependency. Install 'cryptography' package."
    ) from exc


@dataclass
class KeyPair:
    """RSA keypair container."""

    key_id: str
    public_key: bytes
    private_key: bytes


class ConfigStore:
    """Persist agent config with PQC-encrypted API keys."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.config_path = workspace_root / "data" / "config" / "agent-config.json"
        self.keys_dir = workspace_root / "data" / "config" / "keys"
        self.keys_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> Dict[str, Any]:
        """Load config or return defaults."""

        if self.config_path.exists():
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        return {
            "agents": {},
            "loop": {
                "global_loop_budget": 3,
                "retry_count_max": 2,
            },
            "key_store": {
                "active_key_id": None,
            },
        }

    def save_config(self, config: Dict[str, Any]) -> None:
        """Save config to disk."""

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    def _key_path(self, key_id: str) -> Path:
        return self.keys_dir / f"rsa_{key_id}.json"

    def _load_or_create_keypair(self, config: Dict[str, Any]) -> KeyPair:
        """Load RSA keypair or create a new one."""

        key_id = config.get("key_store", {}).get("active_key_id")
        if key_id:
            key_path = self._key_path(key_id)
            if key_path.exists():
                data = json.loads(key_path.read_text(encoding="utf-8"))
                public_key = serialization.load_pem_public_key(
                    base64.b64decode(data["public_key"]),
                    backend=default_backend()
                )
                private_key = serialization.load_pem_private_key(
                    base64.b64decode(data["private_key"]),
                    password=None,
                    backend=default_backend()
                )
                return KeyPair(
                    key_id=key_id,
                    public_key=public_key.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo
                    ),
                    private_key=private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.NoEncryption()
                    ),
                )

        # Generate new RSA keypair
        private_key_obj = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_key_obj = private_key_obj.public_key()
        
        public_key_pem = public_key_obj.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_key_pem = private_key_obj.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        key_id = base64.urlsafe_b64encode(os.urandom(9)).decode("ascii").rstrip("=")
        key_path = self._key_path(key_id)
        key_path.write_text(
            json.dumps(
                {
                    "public_key": base64.b64encode(public_key_pem).decode("ascii"),
                    "private_key": base64.b64encode(private_key_pem).decode("ascii"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        config.setdefault("key_store", {})["active_key_id"] = key_id
        return KeyPair(key_id=key_id, public_key=public_key_pem, private_key=private_key_pem)

    def encrypt_api_key(self, plaintext: str, config: Dict[str, Any]) -> Dict[str, str]:
        """Encrypt API key using RSA-OAEP + AES-GCM hybrid encryption.
        
        1. Generate random AES key
        2. Encrypt data with AES-GCM
        3. Encrypt AES key with RSA-OAEP
        """

        keypair = self._load_or_create_keypair(config)
        
        # Generate AES key and encrypt plaintext
        aes_key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        aesgcm = AESGCM(aes_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        
        # Encrypt AES key with RSA
        public_key_obj = serialization.load_pem_public_key(
            keypair.public_key,
            backend=default_backend()
        )
        encrypted_aes_key = public_key_obj.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        return {
            "key_id": keypair.key_id,
            "encrypted_aes_key": base64.b64encode(encrypted_aes_key).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

    def decrypt_api_key(self, enc: Dict[str, str], config: Dict[str, Any]) -> Optional[str]:
        """Decrypt API key using stored RSA keypair."""

        key_id = enc.get("key_id")
        if not key_id:
            return None
        key_path = self._key_path(key_id)
        if not key_path.exists():
            return None
            
        data = json.loads(key_path.read_text(encoding="utf-8"))
        private_key_obj = serialization.load_pem_private_key(
            base64.b64decode(data["private_key"]),
            password=None,
            backend=default_backend()
        )
        
        # Decrypt AES key with RSA
        encrypted_aes_key = base64.b64decode(enc["encrypted_aes_key"])
        aes_key = private_key_obj.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # Decrypt plaintext with AES
        aesgcm = AESGCM(aes_key)
        nonce = base64.b64decode(enc["nonce"])
        ciphertext = base64.b64decode(enc["ciphertext"])
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
