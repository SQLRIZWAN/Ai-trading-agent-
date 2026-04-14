"""
encryption.py — AES-256 (Fernet) encrypt/decrypt for exchange API keys.
Keys are encrypted client-side in the dashboard before being stored in
Firestore, and decrypted here inside GitHub Actions at trade time.
"""

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from password + salt using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt(plaintext: str, password: str) -> str:
    """Encrypt plaintext with password; returns 'salt$ciphertext' (base64)."""
    salt = os.urandom(16)
    key = _derive_key(password, salt)
    token = Fernet(key).encrypt(plaintext.encode())
    salt_b64 = base64.urlsafe_b64encode(salt).decode()
    token_b64 = token.decode()
    return f"{salt_b64}${token_b64}"


def decrypt(payload: str, password: str) -> str:
    """Decrypt a payload produced by encrypt()."""
    salt_b64, token_b64 = payload.split("$", 1)
    salt = base64.urlsafe_b64decode(salt_b64)
    key = _derive_key(password, salt)
    plaintext = Fernet(key).decrypt(token_b64.encode())
    return plaintext.decode()


def generate_key() -> str:
    """Generate a fresh Fernet key (use once, store in GitHub Secrets)."""
    return Fernet.generate_key().decode()
