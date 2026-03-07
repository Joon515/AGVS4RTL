#!/usr/bin/env python3
"""Test encryption/decryption functionality."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ui.config_store import ConfigStore


def test_encryption():
    """Test API key encryption and decryption."""
    print("=" * 60)
    print("Testing API Key Encryption")
    print("=" * 60)
    
    store = ConfigStore(workspace_root=PROJECT_ROOT)
    config = store.load_config()
    
    # Test API key
    test_key = "sk-test-1234567890abcdefghijklmnopqrstuvwxyz"
    print(f"\n📝 Original API Key: {test_key[:20]}...")
    
    # Encrypt
    encrypted = store.encrypt_api_key(test_key, config)
    print(f"\n🔒 Encrypted data:")
    print(f"   Key ID: {encrypted['key_id']}")
    print(f"   Encrypted AES Key: {encrypted['encrypted_aes_key'][:40]}...")
    print(f"   Nonce: {encrypted['nonce']}")
    print(f"   Ciphertext: {encrypted['ciphertext'][:40]}...")
    
    # Decrypt
    decrypted = store.decrypt_api_key(encrypted, config)
    if decrypted is None:
        print("\n❌ Decryption returned None")
        return False
    print(f"\n🔓 Decrypted API Key: {decrypted[:20]}...")
    
    # Verify
    if decrypted == test_key:
        print("\n✅ Encryption/Decryption test PASSED!")
        return True
    else:
        print("\n❌ Encryption/Decryption test FAILED!")
        print(f"   Expected: {test_key}")
        print(f"   Got: {decrypted}")
        return False


if __name__ == "__main__":
    success = test_encryption()
    sys.exit(0 if success else 1)
