"""Password encryption utilities for secure credential storage"""
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import os
from pathlib import Path


class PasswordManager:
    """Manages encryption/decryption of sensitive data like database passwords"""
    
    def __init__(self, app_data_dir: Path = None):
        """Initialize password manager with encryption key"""
        if app_data_dir is None:
            app_data_dir = Path.home() / ".wp_local_installer"
        
        app_data_dir.mkdir(parents=True, exist_ok=True)
        self.key_file = app_data_dir / ".secure_key"
        
        # Generate or load encryption key
        if self.key_file.exists():
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            # Generate a new key based on machine-specific data
            key = self._generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            # Make file read-only for security
            os.chmod(self.key_file, 0o600)
        
        self.cipher = Fernet(key)
    
    def _generate_key(self) -> bytes:
        """Generate encryption key from machine-specific data"""
        # Use computer name + user name as salt
        import socket
        import getpass
        
        salt_data = f"{socket.gethostname()}-{getpass.getuser()}".encode()
        
        # Generate a random password
        password = os.urandom(32)
        
        # Derive key using PBKDF2HMAC
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt_data,
            iterations=100000,
            backend=default_backend()
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext password"""
        if not plaintext:
            return ""
        
        encrypted = self.cipher.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt(self, encrypted_text: str) -> str:
        """Decrypt encrypted password"""
        if not encrypted_text:
            return ""
        
        try:
            decoded = base64.urlsafe_b64decode(encrypted_text.encode())
            decrypted = self.cipher.decrypt(decoded)
            return decrypted.decode()
        except Exception:
            # If decryption fails, assume it's plaintext (for backward compatibility)
            return encrypted_text
    
    def is_encrypted(self, text: str) -> bool:
        """Check if text is encrypted"""
        try:
            if not text:
                return False
            decoded = base64.urlsafe_b64decode(text.encode())
            self.cipher.decrypt(decoded)
            return True
        except Exception:
            return False


# Global instance
_password_manager = None

def get_password_manager() -> PasswordManager:
    """Get or create global password manager instance"""
    global _password_manager
    if _password_manager is None:
        _password_manager = PasswordManager()
    return _password_manager
