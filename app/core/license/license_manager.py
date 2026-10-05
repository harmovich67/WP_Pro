"""
License Manager Module
Handles license activation, verification, and storage.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
import urllib.request
import urllib.error

from .encryption import LicenseEncryption, get_machine_id, create_offline_token, verify_offline_token
from .feature_flags import FeatureFlags, FEATURE_TIERS, TRIAL_DAYS, PRICING
from app.core.i18n import t as tr


# API endpoint for license verification.
# Points at the PHP license server deployed on InfinityFree (see license_dashboard_php/README.md).
LICENSE_API_URL = os.environ.get("LICENSE_API_URL", "https://ser.42web.io/tafeal/api/index.php?route=")

# Local storage paths
def _get_license_dir() -> Path:
    """Get the license storage directory."""
    if os.name == 'nt':  # Windows
        base = Path(os.environ.get('APPDATA', Path.home()))
    else:  # Linux/Mac
        base = Path.home() / '.config'
    
    license_dir = base / 'HarmulizerPro' / 'license'
    license_dir.mkdir(parents=True, exist_ok=True)
    return license_dir


LICENSE_FILE = _get_license_dir() / 'license.dat'
OFFLINE_TOKEN_FILE = _get_license_dir() / 'offline.dat'


@dataclass
class LicenseInfo:
    """License information structure."""
    license_key: str = ""
    tier: str = "free"
    email: str = ""
    activated_at: str = ""
    expires_at: str = ""
    is_trial: bool = False
    trial_started_at: str = ""
    machine_id: str = ""
    last_verified: str = ""
    custom_features: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.custom_features is None:
            self.custom_features = {}
    
    def is_expired(self) -> bool:
        """Check if the license is expired."""
        if not self.expires_at:
            return False
        
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.utcnow() > expires
        except:
            return False
    
    def is_trial_expired(self) -> bool:
        """Check if the trial period is expired."""
        if not self.is_trial or not self.trial_started_at:
            return False
        
        try:
            started = datetime.fromisoformat(self.trial_started_at)
            trial_end = started + timedelta(days=TRIAL_DAYS)
            return datetime.utcnow() > trial_end
        except:
            return True
    
    def trial_days_remaining(self) -> int:
        """Get remaining trial days."""
        if not self.is_trial or not self.trial_started_at:
            return 0
        
        try:
            started = datetime.fromisoformat(self.trial_started_at)
            trial_end = started + timedelta(days=TRIAL_DAYS)
            remaining = (trial_end - datetime.utcnow()).days
            return max(0, remaining)
        except:
            return 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LicenseInfo':
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class LicenseManager:
    """
    Manages license activation, verification, and feature access.
    """
    
    def __init__(self):
        self._encryption = LicenseEncryption()
        self._machine_id = get_machine_id()
        self._license_info: Optional[LicenseInfo] = None
        self._feature_flags: Optional[FeatureFlags] = None
        self._load_license()
    
    @property
    def machine_id(self) -> str:
        """Get the machine ID."""
        return self._machine_id
    
    @property
    def license_info(self) -> LicenseInfo:
        """Get current license info."""
        if self._license_info is None:
            return LicenseInfo()
        return self._license_info
    
    @property
    def feature_flags(self) -> FeatureFlags:
        """Get feature flags for current license."""
        if self._feature_flags is None:
            tier = self._license_info.tier if self._license_info else "free"
            custom = self._license_info.custom_features if self._license_info else {}
            self._feature_flags = FeatureFlags(tier=tier, custom_overrides=custom)
        return self._feature_flags
    
    def _load_license(self) -> bool:
        """Load license from local storage."""
        try:
            if not LICENSE_FILE.exists():
                return False
            
            encoded = LICENSE_FILE.read_text(encoding='utf-8')
            data = self._encryption.decode_license(encoded)
            
            if data:
                self._license_info = LicenseInfo.from_dict(data)
                self._feature_flags = None  # Reset to recalculate
                return True
        except Exception as e:
            print(f"Error loading license: {e}")
        
        return False
    
    def _save_license(self) -> bool:
        """Save license to local storage."""
        try:
            if self._license_info is None:
                return False
            
            encoded = self._encryption.encode_license(self._license_info.to_dict())
            LICENSE_FILE.write_text(encoded, encoding='utf-8')
            return True
        except Exception as e:
            print(f"Error saving license: {e}")
            return False
    
    def is_licensed(self) -> bool:
        """Check if there's a valid license."""
        if self._license_info is None:
            return False
        
        # Check trial expiration
        if self._license_info.is_trial and self._license_info.is_trial_expired():
            return False
        
        # Check license expiration
        if self._license_info.is_expired():
            return False
        
        return True
    
    def get_tier(self) -> str:
        """Get current license tier."""
        if not self.is_licensed():
            return "free"
        return self._license_info.tier if self._license_info else "free"
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled."""
        return self.feature_flags.is_enabled(feature)
    
    def get_max_projects(self) -> int:
        """Get maximum allowed projects."""
        return self.feature_flags.get_max_projects()
    
    def start_trial(self, tier: str = "pro") -> bool:
        """Start a trial period."""
        # Check if trial was already used
        if self._license_info and self._license_info.trial_started_at:
            return False
        
        self._license_info = LicenseInfo(
            tier=tier,
            is_trial=True,
            trial_started_at=datetime.utcnow().isoformat(),
            machine_id=self._machine_id
        )
        self._feature_flags = None
        return self._save_license()
    
    def activate(self, license_key: str, email: str = "") -> tuple[bool, str]:
        """
        Activate a license key.
        Returns (success, message).
        """
        # Try online activation first
        try:
            result = self._verify_online(license_key)
            if result.get("success"):
                self._license_info = LicenseInfo(
                    license_key=license_key,
                    tier=result.get("tier", "basic"),
                    email=email or result.get("email", ""),
                    activated_at=datetime.utcnow().isoformat(),
                    expires_at=result.get("expires_at", ""),
                    machine_id=self._machine_id,
                    last_verified=datetime.utcnow().isoformat(),
                    custom_features=result.get("custom_features", {})
                )
                self._feature_flags = None
                self._save_license()
                
                # Create offline token
                self._save_offline_token()
                
                return True, tr("تم تفعيل الترخيص بنجاح! 🎉")
            else:
                return False, result.get("message", tr("مفتاح الترخيص غير صالح"))
        except Exception as e:
            return False, f"{tr('خطأ في الاتصال بالخادم: ')}{str(e)}"
    
    def _make_api_request(self, url: str, data: bytes) -> dict:
        import re
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read()
                html = content.decode('utf-8', errors='ignore')
        except urllib.error.URLError as e:
            raise e
        except Exception as e:
            raise Exception("Network error")
            
        try:
            return json.loads(html)
        except Exception:
            a_match = re.search(r'a=toNumbers\("([a-f0-9]+)"\)', html)
            b_match = re.search(r'b=toNumbers\("([a-f0-9]+)"\)', html)
            c_match = re.search(r'c=toNumbers\("([a-f0-9]+)"\)', html)
            if a_match and b_match and c_match:
                try:
                    a = bytes.fromhex(a_match.group(1))
                    b = bytes.fromhex(b_match.group(1))
                    c = bytes.fromhex(c_match.group(1))
                    cipher = Cipher(algorithms.AES(a), modes.CBC(b), backend=default_backend())
                    decryptor = cipher.decryptor()
                    cookie = (decryptor.update(c) + decryptor.finalize()).hex()
                    
                    req.add_header('Cookie', f'__test={cookie}')
                    with urllib.request.urlopen(req, timeout=15) as response2:
                        return json.loads(response2.read().decode('utf-8'))
                except Exception as bypass_e:
                    raise Exception("Failed to bypass server security") from bypass_e
            
            raise Exception("Invalid server response format")

    def _verify_online(self, license_key: str) -> dict:
        """Verify license with online server."""
        try:
            url = f"{LICENSE_API_URL}/verify"
            data = json.dumps({
                "license_key": license_key,
                "machine_id": self._machine_id
            }).encode('utf-8')
            return self._make_api_request(url, data)
        except urllib.error.URLError:
            # If server is unreachable, check offline token
            return self._verify_offline(license_key)
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def _verify_offline(self, license_key: str = None) -> dict:
        """Verify using offline token."""
        try:
            if not OFFLINE_TOKEN_FILE.exists():
                return {"success": False, "message": tr("لا يوجد توكن للعمل بدون اتصال")}
            
            token = OFFLINE_TOKEN_FILE.read_text(encoding='utf-8')
            data = verify_offline_token(token, self._machine_id)
            
            if data:
                return {
                    "success": True,
                    "tier": self._license_info.tier if self._license_info else "basic",
                    "offline": True
                }
            
            return {"success": False, "message": tr("توكن العمل بدون اتصال منتهي الصلاحية")}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def _save_offline_token(self) -> bool:
        """Save offline token for working without internet."""
        try:
            if not self._license_info or not self._license_info.license_key:
                return False
            
            token = create_offline_token(
                self._license_info.license_key,
                self._machine_id,
                days_valid=30  # 30 days offline validity
            )
            OFFLINE_TOKEN_FILE.write_text(token, encoding='utf-8')
            return True
        except:
            return False
    
    def refresh_license(self) -> tuple[bool, str]:
        """
        Refresh license status from server.
        Called periodically (monthly as per requirements).
        """
        if not self._license_info or not self._license_info.license_key:
            return False, tr("لا يوجد ترخيص لتحديثه")
        
        return self.activate(self._license_info.license_key, self._license_info.email)
    
    def should_verify(self) -> bool:
        """Check if we should verify the license (monthly)."""
        if not self._license_info or not self._license_info.last_verified:
            return True
        
        try:
            last = datetime.fromisoformat(self._license_info.last_verified)
            return (datetime.utcnow() - last).days >= 30
        except:
            return True
    
    def deactivate(self) -> bool:
        """Deactivate the current license."""
        try:
            # Try to notify server
            if self._license_info and self._license_info.license_key:
                try:
                    url = f"{LICENSE_API_URL}/deactivate"
                    data = json.dumps({
                        "license_key": self._license_info.license_key,
                        "machine_id": self._machine_id
                    }).encode('utf-8')
                    self._make_api_request(url, data)
                except Exception as e:
                    print(f"Failed to notify server of deactivation: {e}")
            
            # Clear local data
            if LICENSE_FILE.exists():
                LICENSE_FILE.unlink()
            if OFFLINE_TOKEN_FILE.exists():
                OFFLINE_TOKEN_FILE.unlink()
            
            self._license_info = None
            self._feature_flags = None
            
            return True
        except Exception as e:
            print(f"Error deactivating: {e}")
            return False
    
    def reset_license(self) -> bool:
        """
        إعادة ضبط كاملة للترخيص - يحذف كل شيء بما فيها التجربة.
        يسمح ببدء تجربة جديدة.
        """
        try:
            # Clear local files
            if LICENSE_FILE.exists():
                LICENSE_FILE.unlink()
            if OFFLINE_TOKEN_FILE.exists():
                OFFLINE_TOKEN_FILE.unlink()
            
            # Reset internal state
            self._license_info = None
            self._feature_flags = None
            
            print("License has been fully reset.")
            return True
        except Exception as e:
            print(f"Error resetting license: {e}")
            return False

    
    def get_whatsapp_message(self, tier: str = "pro") -> str:
        """
        Generate WhatsApp message for license purchase.
        """
        price = PRICING.get(tier, {}).get("price", 200)
        tier_name = {
            "basic": tr("الأساسي"),
            "pro": tr("الاحترافي"),
            "enterprise": tr("المؤسسي")
        }.get(tier, tr("الاحترافي"))
        
        message = f"""مرحباً! 👋

أريد شراء ترخيص Harmulizer Pro

📦 الخطة: {tier_name}
💰 السعر: ${price}/شهر
🖥️ Machine ID: {self._machine_id}

شكراً لكم!"""
        
        return message
    
    def get_whatsapp_url(self, tier: str = "pro", phone: str = "") -> str:
        """
        Get WhatsApp URL for license purchase.
        """
        import urllib.parse
        message = self.get_whatsapp_message(tier)
        encoded = urllib.parse.quote(message)
        return f"https://wa.me/{phone}?text={encoded}"
    
    def get_status_display(self) -> dict:
        """Get license status for display in UI."""
        if self._license_info is None or not self.is_licensed():
            return {
                "status": tr("غير مفعّل"),
                "tier": tr("مجاني"),
                "icon": "⚪",
                "color": "#888888",
                "message": tr("قم بتفعيل الترخيص للحصول على جميع الميزات")
            }
        
        tier_display = {
            "free": (tr("مجاني"), "⚪", "#888888"),
            "basic": (tr("أساسي"), "🔵", "#3498db"),
            "pro": (tr("احترافي"), "🟡", "#f39c12"),
            "enterprise": (tr("مؤسسي"), "🟢", "#27ae60")
        }
        
        tier = self._license_info.tier
        name, icon, color = tier_display.get(tier, tier_display["free"])
        
        if self._license_info.is_trial:
            days = self._license_info.trial_days_remaining()
            return {
                "status": tr("فترة تجريبية"),
                "tier": f"{name}{tr(' (تجريبي)')}",
                "icon": "⏳",
                "color": "#e74c3c",
                "message": f"{tr('متبقي ')}{days}{tr(' يوم من الفترة التجريبية')}"
            }
        
        return {
            "status": tr("مفعّل"),
            "tier": name,
            "icon": icon,
            "color": color,
            "message": f"{tr('الترخيص: ')}{self._encryption.obfuscate_key(self._license_info.license_key)}"
        }
