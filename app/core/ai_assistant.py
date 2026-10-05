"""
Gemini AI Integration Module
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Callable
from app.core.i18n import t as tr

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

LogFn = Callable[[str], None]

class GeminiAssistant:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = None
        
        if GEMINI_AVAILABLE and self.api_key:
            try:
                import warnings
                warnings.filterwarnings('ignore')
                
                genai.configure(api_key=self.api_key)
                
                # Dynamic Model Discovery
                model_name = 'gemini-1.5-flash'
                try:
                    for m in genai.list_models():
                        if 'generateContent' in m.supported_generation_methods:
                            model_name = m.name
                            break
                except Exception:
                    pass
                
                self.model = genai.GenerativeModel(model_name)
            except Exception:
                self.model = None

    def is_ready(self) -> bool:
        """Check if Gemini is configured and ready"""
        return self.model is not None

    def analyze_debug_log(self, log_content: str) -> str:
        """Analyze WordPress debug log using AI"""
        if not self.is_ready():
            return tr("❌ Gemini AI غير مُعد. يرجى ضبط مفتاح API.")
        
        prompt = f"""أنت خبير WordPress متخصص في تحليل الأخطاء.
قم بتحليل سجل الأخطاء التالي وقدم:
1. ملخص للأخطاء الموجودة
2. الأخطاء الحرجة (إن وجدت)
3. اقتراحات للإصلاح بالعربية

سجل الأخطاء:
{log_content[:5000]}

الرد بالعربية فقط."""

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"{tr('❌ خطأ في التحليل: ')}{str(e)}"

    def security_scan_code(self, code_snippet: str, file_path: str = "") -> str:
        """Scan code for security issues"""
        if not self.is_ready():
            return tr("❌ Gemini AI غير مُعد.")

        prompt = f"""أنت خبير أمان WordPress. قم بفحص الكود التالي بحثاً عن:
1. ثغرات أمنية (SQL Injection, XSS, etc.)
2. كود مشبوه أو خطير
3. ممارسات غير آمنة

الملف: {file_path}
الكود:
{code_snippet[:3000]}

قدم تقريراً بالعربية."""

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"{tr('❌ خطأ: ')}{str(e)}"

    def performance_suggestions(self, project_info: dict) -> str:
        """Get performance optimization suggestions"""
        if not self.is_ready():
            return tr("❌ Gemini AI غير مُعد.")

        prompt = f"""أنت خبير في تحسين أداء WordPress. بناءً على المعلومات التالية:
- المشروع: {project_info.get('name', 'Unknown')}
- المسار: {project_info.get('path', '')}
- URL: {project_info.get('url', '')}

قدم 5 اقتراحات محددة لتحسين الأداء بالعربية."""

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"{tr('❌ خطأ: ')}{str(e)}"

    def chat(self, message: str, context: str = "") -> str:
        """General chat about WordPress issues"""
        if not self.is_ready():
            return tr("❌ Gemini AI غير مُعد. يرجى إضافة مفتاح API في الإعدادات.")
        
        prompt = f"""أنت مساعد WordPress خبير. أجب على السؤال التالي بالعربية:

السياق: {context}

السؤال: {message}"""

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"{tr('❌ خطأ: ')}{str(e)}"
