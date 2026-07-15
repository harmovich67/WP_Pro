"""
License Encryption Module
Handles secure storage and verification of license data.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import platform
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

# Secret key for HMAC signing (in production, this should be more secure)
_SECRET_KEY = b"H4rMu1!z3r_Pr0_L!c3ns3_K3y_2024_S3cur3"


def get_machine_id() -> str:
    """
    Generate a unique machine identifier.
    Combines multiple system identifiers to create a stable fingerprint.
    """
    components = []
    
    # MAC address (UUID node)
    try:
        mac = uuid.getnode()
        components.append(str(mac))
    except:
        pass
    
    # Hostname
    try:
        components.append(platform.node())
    except:
        pass
    
    # Platform info
    try:
        components.append(platform.system())
        components.append(platform.machine())
    except:
        pass
    
    # Create deterministic hash
    combined = "-".join(components)
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


class LicenseEncryption:
    """Handles encryption, signing, and verification of license data."""
    
    def __init__(self, secret_key: bytes = None):
        self._key = secret_key or _SECRET_KEY
    
    def _create_signature(self, data: str) -> str:
        """Create HMAC signature for data."""
        signature = hmac.new(self._key, data.encode(), hashlib.sha256)
        return signature.hexdigest()
    
    def _verify_signature(self, data: str, signature: str) -> bool:
        """Verify HMAC signature."""
        expected = self._create_signature(data)
        return hmac.compare_digest(expected, signature)
    
    def encode_license(self, license_data: Dict[str, Any]) -> str:
        """
        Encode and sign license data.
        Returns a base64 encoded string that includes the signature.
        """
        # Add timestamp
        license_data["encoded_at"] = datetime.utcnow().isoformat()
        
        # Convert to JSON
        json_data = json.dumps(license_data, sort_keys=True)
        
        # Create signature
        signature = self._create_signature(json_data)
        
        # Combine data and signature
        combined = {
            "data": license_data,
            "signature": signature
        }
        
        # Encode to base64
        encoded = base64.b64encode(json.dumps(combined).encode()).decode()
        return encoded
    
    def decode_license(self, encoded: str) -> Optional[Dict[str, Any]]:
        """
        Decode and verify license data.
        Returns None if verification fails.
        """
        try:
            # Decode base64
            decoded = base64.b64decode(encoded.encode()).decode()
            combined = json.loads(decoded)
            
            # Extract data and signature
            data = combined.get("data", {})
            signature = combined.get("signature", "")
            
            # Verify signature
            json_data = json.dumps(data, sort_keys=True)
            if not self._verify_signature(json_data, signature):
                return None
            
            return data
        except Exception:
            return None
    
    def generate_license_key(self, tier: str = "pro") -> str:
        """
        Generate a unique license key.
        Format: HMP-XXXX-XXXX-XXXX-XXXX
        """
        tier_prefix = {
            "free": "HMF",
            "basic": "HMB", 
            "pro": "HMP",
            "enterprise": "HME"
        }.get(tier, "HMP")
        
        # Generate random segments
        segments = []
        for _ in range(4):
            segment = uuid.uuid4().hex[:4].upper()
            segments.append(segment)
        
        return f"{tier_prefix}-{'-'.join(segments)}"
    
    def obfuscate_key(self, key: str) -> str:
        """Obfuscate license key for display (show only last 4 chars)."""
        if len(key) < 8:
            return "*" * len(key)
        return "*" * (len(key) - 4) + key[-4:]


def create_offline_token(license_key: str, machine_id: str, days_valid: int = 30) -> str:
    """
    Create an offline validation token.
    This allows the app to work offline for the specified number of days.
    """
    encryption = LicenseEncryption()
    
    data = {
        "license_key": license_key,
        "machine_id": machine_id,
        "valid_until": (datetime.utcnow().timestamp() + (days_valid * 86400)),
        "type": "offline_token"
    }
    
    return encryption.encode_license(data)


def verify_offline_token(token: str, machine_id: str) -> Optional[Dict[str, Any]]:
    """
    Verify an offline validation token.
    Returns None if invalid or expired.
    """
    encryption = LicenseEncryption()
    
    data = encryption.decode_license(token)
    if not data:
        return None
    
    # Verify machine ID
    if data.get("machine_id") != machine_id:
        return None
    
    # Check expiration
    valid_until = data.get("valid_until", 0)
    if datetime.utcnow().timestamp() > valid_until:
        return None
    
    return data
