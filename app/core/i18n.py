"""
Lightweight i18n for the app.

Design: Arabic is the canonical source language (all UI strings are written in
Arabic at the call site, matching the app's existing code). `t()` looks the
Arabic source string up in TRANSLATIONS to get the English version when the
current language is English, and returns the Arabic text unchanged otherwise.
This lets call sites stay as plain `t("النص العربي")` without inventing
abstract string keys, and keeps the two languages' text next to each other in
one dict instead of scattered across every file.
"""
from PyQt6.QtCore import QSettings

_settings = QSettings("Harmulizer", "LanguagePreference")
_current_language = "ar"


def load_language() -> str:
    """Load the saved language preference (call once at app startup)."""
    global _current_language
    _current_language = _settings.value("language", "ar")
    return _current_language


def get_language() -> str:
    return _current_language


def set_language(lang: str) -> None:
    global _current_language
    _current_language = lang
    _settings.setValue("language", lang)


def t(text: str) -> str:
    """Translate an Arabic source string to the current language."""
    if _current_language == "en":
        return TRANSLATIONS.get(text, text)
    return text


# Arabic source string -> English translation.
TRANSLATIONS: dict[str, str] = {
    "معالج الإعداد • القوالب • أدوات قاعدة البيانات • استنساخ/نسخ احتياطي • طرفية WP-CLI":
        "Setup Wizard • Templates • Database Tools • Clone/Backup • WP-CLI Terminal",
    "إدارة الترخيص": "License Management",
    "حول البرنامج": "About",
    "حول Harmulizer Pro": "About Harmulizer Pro",
    "تبديل اللغة": "Switch Language",
    "جاهز": "Ready",
}
