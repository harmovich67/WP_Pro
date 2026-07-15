"""
Feature Flags Module
Defines which features are available for each license tier.
Override configuration is loaded from ~/.harmulizer_pro/feature_config.json
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

# ── Config file location ───────────────────────────────────────────────────────
_CONFIG_DIR  = Path.home() / ".harmulizer_pro"
_CONFIG_FILE = _CONFIG_DIR / "feature_config.json"

# Default developer password hash (sha256 of "harmulizer2024")
_DEFAULT_DEV_HASH = hashlib.sha256(b"harmulizer2024").hexdigest()

# ── Pricing Information ────────────────────────────────────────────────────────
PRICING = {
    "free":       {"price": 0,   "currency": "USD", "period": None},
    "basic":      {"price": 50,  "currency": "USD", "period": "month"},
    "pro":        {"price": 200, "currency": "USD", "period": "month"},
    "enterprise": {"price": 400, "currency": "USD", "period": "month"},
}

# Trial period in days
TRIAL_DAYS = 3

# ── Feature definitions for each tier (DEFAULTS) ──────────────────────────────
FEATURE_TIERS: Dict[str, Dict[str, Any]] = {
    "free": {
        "dashboard": True,
        "wizard": True,
        "max_projects": 1,
        "wpcli_console": False,
        "project_tools": False,
        "backup": False,
        "scheduled_backup": False,
        "database_viewer": False,
        "url_converter": False,
        "security": False,
        "manager": False,
        "config_editor": False,
        "devtools": False,
        "ai_assistant": False,
        "monitoring": False,
        "site_dashboard": False,
    },
    "basic": {
        "dashboard": True,
        "wizard": True,
        "max_projects": 3,
        "wpcli_console": True,
        "project_tools": True,
        "backup": True,
        "scheduled_backup": False,
        "database_viewer": False,
        "url_converter": True,
        "security": False,
        "manager": False,
        "config_editor": False,
        "devtools": False,
        "ai_assistant": False,
        "monitoring": False,
        "site_dashboard": True,
    },
    "pro": {
        "dashboard": True,
        "wizard": True,
        "max_projects": -1,
        "wpcli_console": True,
        "project_tools": True,
        "backup": True,
        "scheduled_backup": True,
        "database_viewer": True,
        "url_converter": True,
        "security": True,
        "manager": True,
        "config_editor": True,
        "devtools": False,
        "ai_assistant": False,
        "monitoring": False,
        "site_dashboard": True,
    },
    "enterprise": {
        "dashboard": True,
        "wizard": True,
        "max_projects": -1,
        "wpcli_console": True,
        "project_tools": True,
        "backup": True,
        "scheduled_backup": True,
        "database_viewer": True,
        "url_converter": True,
        "security": True,
        "manager": True,
        "config_editor": True,
        "devtools": True,
        "ai_assistant": True,
        "monitoring": True,
        "site_dashboard": True,
    },
}

# ── Feature display names (for UI) ────────────────────────────────────────────
FEATURE_NAMES = {
    "dashboard":       "لوحة التحكم",
    "wizard":          "معالج التثبيت",
    "max_projects":    "عدد المشاريع",
    "wpcli_console":   "WP-CLI Console",
    "project_tools":   "أدوات المشروع",
    "backup":          "النسخ الاحتياطي",
    "scheduled_backup":"الجدولة التلقائية",
    "database_viewer": "عارض قاعدة البيانات",
    "url_converter":   "محول الروابط",
    "security":        "أدوات الأمان",
    "manager":         "إدارة الإضافات والقوالب",
    "config_editor":   "محرر الإعدادات",
    "devtools":        "أدوات المطورين",
    "ai_assistant":    "المساعد الذكي",
    "monitoring":      "المراقبة",
    "site_dashboard":  "لوحة تحكم الموقع المصغرة",
}

# Tier display names
TIER_NAMES = {
    "free":       "مجاني",
    "basic":      "أساسي",
    "pro":        "احترافي",
    "enterprise": "مؤسسي",
}


# ══════════════════════════════════════════════════════════════════════════════
# Override persistence helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_default_feature_tiers() -> Dict[str, Dict[str, Any]]:
    """Return a deep copy of the built-in default FEATURE_TIERS."""
    return copy.deepcopy({
        "free": {
            "dashboard": True, "wizard": True, "max_projects": 1,
            "wpcli_console": False, "project_tools": False, "backup": False,
            "scheduled_backup": False, "database_viewer": False,
            "url_converter": False, "security": False, "manager": False,
            "config_editor": False, "devtools": False, "ai_assistant": False,
            "monitoring": False, "site_dashboard": False,
        },
        "basic": {
            "dashboard": True, "wizard": True, "max_projects": 3,
            "wpcli_console": True, "project_tools": True, "backup": True,
            "scheduled_backup": False, "database_viewer": False,
            "url_converter": True, "security": False, "manager": False,
            "config_editor": False, "devtools": False, "ai_assistant": False,
            "monitoring": False, "site_dashboard": True,
        },
        "pro": {
            "dashboard": True, "wizard": True, "max_projects": -1,
            "wpcli_console": True, "project_tools": True, "backup": True,
            "scheduled_backup": True, "database_viewer": True,
            "url_converter": True, "security": True, "manager": True,
            "config_editor": True, "devtools": False, "ai_assistant": False,
            "monitoring": False, "site_dashboard": True,
        },
        "enterprise": {
            "dashboard": True, "wizard": True, "max_projects": -1,
            "wpcli_console": True, "project_tools": True, "backup": True,
            "scheduled_backup": True, "database_viewer": True,
            "url_converter": True, "security": True, "manager": True,
            "config_editor": True, "devtools": True, "ai_assistant": True,
            "monitoring": True, "site_dashboard": True,
        },
    })


def get_default_pricing() -> Dict[str, Dict[str, Any]]:
    """Return a deep copy of the built-in default PRICING."""
    return copy.deepcopy({
        "free":       {"price": 0,   "currency": "USD", "period": None},
        "basic":      {"price": 50,  "currency": "USD", "period": "month"},
        "pro":        {"price": 200, "currency": "USD", "period": "month"},
        "enterprise": {"price": 400, "currency": "USD", "period": "month"},
    })


def load_config() -> dict:
    """Load the full config JSON file.  Returns {} if not found or corrupt."""
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_config(data: dict):
    """Persist the full config dict to the JSON file."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data["modified_at"] = datetime.datetime.now().isoformat()
    _CONFIG_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_tier_overrides(feature_tiers: Dict[str, Dict[str, Any]],
                        pricing: Dict[str, Dict[str, Any]]):
    """Save feature-tier matrix and pricing to the config file."""
    cfg = load_config()
    cfg["version"] = "1.0"
    cfg["feature_tiers"] = feature_tiers
    cfg["pricing"] = pricing
    save_config(cfg)


def load_and_apply_overrides() -> bool:
    """
    Apply any saved overrides onto the module-level FEATURE_TIERS / PRICING.
    Called automatically when this module is imported.
    Returns True if overrides were applied.
    """
    global FEATURE_TIERS, PRICING
    cfg = load_config()
    if not cfg:
        return False
    changed = False
    for tier, features in cfg.get("feature_tiers", {}).items():
        if tier in FEATURE_TIERS:
            FEATURE_TIERS[tier].update(features)
            changed = True
    for tier, pricing_data in cfg.get("pricing", {}).items():
        if tier in PRICING:
            PRICING[tier].update(pricing_data)
            changed = True
    return changed


def get_dev_password_hash() -> str:
    """Return the stored developer password hash (or default)."""
    return load_config().get("dev_password_hash", _DEFAULT_DEV_HASH)


def set_dev_password_hash(new_hash: str):
    """Persist a new developer password hash."""
    cfg = load_config()
    cfg["dev_password_hash"] = new_hash
    save_config(cfg)


def verify_dev_password(password: str) -> bool:
    """Return True if the given plain-text password matches the stored hash."""
    return hashlib.sha256(password.encode()).hexdigest() == get_dev_password_hash()


# ══════════════════════════════════════════════════════════════════════════════
# FeatureFlags dataclass
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FeatureFlags:
    """Manages feature availability based on license tier."""

    tier: str = "free"
    custom_overrides: Dict[str, Any] = None

    def __post_init__(self):
        if self.custom_overrides is None:
            self.custom_overrides = {}
        if self.tier not in FEATURE_TIERS:
            self.tier = "free"

    def is_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled for the current tier."""
        if feature in self.custom_overrides:
            return bool(self.custom_overrides[feature])
        tier_features = FEATURE_TIERS.get(self.tier, FEATURE_TIERS["free"])
        return bool(tier_features.get(feature, False))

    def get_max_projects(self) -> int:
        """Get the maximum number of projects allowed."""
        if "max_projects" in self.custom_overrides:
            return self.custom_overrides["max_projects"]
        tier_features = FEATURE_TIERS.get(self.tier, FEATURE_TIERS["free"])
        return tier_features.get("max_projects", 1)

    def get_all_features(self) -> Dict[str, Any]:
        """Get all feature states for the current tier."""
        tier_features = FEATURE_TIERS.get(self.tier, FEATURE_TIERS["free"]).copy()
        tier_features.update(self.custom_overrides)
        return tier_features

    def get_disabled_features(self) -> list:
        """Get list of features that are disabled."""
        all_features = self.get_all_features()
        return [k for k, v in all_features.items() if not v and k != "max_projects"]

    def get_upgrade_message(self, feature: str) -> str:
        """Get upgrade message for a locked feature."""
        feature_name = FEATURE_NAMES.get(feature, feature)
        for tier in ["basic", "pro", "enterprise"]:
            if FEATURE_TIERS[tier].get(feature, False):
                tier_name = TIER_NAMES[tier]
                price = PRICING[tier]["price"]
                return (f"ميزة '{feature_name}' تتطلب الترقية إلى "
                        f"{tier_name} (${price}/شهر)")
        return f"ميزة '{feature_name}' غير متاحة في خطتك الحالية"


# ── Auto-apply overrides when module is first imported ────────────────────────
load_and_apply_overrides()
