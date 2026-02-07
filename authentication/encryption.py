"""
Encryption utilities for secure token storage.
"""

import os
import base64
from cryptography.fernet import Fernet
from django.conf import settings


class TokenEncryption:
    """Handles encryption and decryption of OAuth tokens."""
    
    def __init__(self):
        key = settings.ENCRYPTION_KEY
        if not key:
            # Generate a key for development (should be set in production)
            key = Fernet.generate_key().decode()
        
        # Ensure key is properly formatted
        if isinstance(key, str):
            key = key.encode()
        
        self._fernet = Fernet(key)
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string."""
        if not plaintext:
            return ''
        return self._fernet.encrypt(plaintext.encode()).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt an encrypted string."""
        if not ciphertext:
            return ''
        return self._fernet.decrypt(ciphertext.encode()).decode()


# Singleton instance
_encryption = None


def get_encryption():
    """Get the singleton encryption instance."""
    global _encryption
    if _encryption is None:
        _encryption = TokenEncryption()
    return _encryption


def encrypt_token(token: str) -> str:
    """Encrypt a token for storage."""
    return get_encryption().encrypt(token)


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a stored token."""
    return get_encryption().decrypt(encrypted_token)
