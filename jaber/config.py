"""Jaber-এর সেটিংস: %APPDATA%\\Jaber\\config.json ফাইলে সেভ থাকে।"""
import json
import os
import sys
from pathlib import Path

APP_NAME = "Jaber"


def app_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def documents_dir() -> Path:
    d = Path.home() / "Documents" / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


# OpenAI-compatible প্রোভাইডার। মডেলের নাম বদলালে সেটিংসে "মডেল লোড" চাপলেই নতুন লিস্ট আসবে।
PROVIDERS = {
    "Groq (ফ্রি)": {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b"},
    "OpenRouter (ফ্রি মডেল)": {"base_url": "https://openrouter.ai/api/v1", "model": "openrouter/auto"},
    "Google Gemini (ফ্রি)": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "model": "gemini-2.5-flash"},
    "xAI Grok": {"base_url": "https://api.x.ai/v1", "model": "grok-3-mini"},
    "Ollama (অফলাইন, নিজের পিসিতে)": {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:7b"},
    "Custom": {"base_url": "", "model": ""},
}

DEFAULTS = {
    "provider": "Groq (ফ্রি)",
    "base_url": PROVIDERS["Groq (ফ্রি)"]["base_url"],
    "api_key": "",
    "model": PROVIDERS["Groq (ফ্রি)"]["model"],
    # ভয়েস (Speech-to-Text) সবসময় Groq Whisper দিয়ে – ফ্রি Groq key লাগে
    "groq_key_for_voice": "",
    "stt_model": "whisper-large-v3-turbo",
    "stt_language": "",  # খালি = অটো (বাংলা+ইংরেজি মিশ্র)
    "tts_enabled": True,
    "tts_voice": "bn-BD-NabanitaNeural",
    "wake_word_enabled": False,
    "wake_words": ["jaber", "jabber", "jabir", "zaber", "জাবের", "জাবির", "যাবের", "জেবার"],
    "mic_threshold": 0,  # 0 = অটো ক্যালিব্রেট
    "daily_news_enabled": True,
    "daily_news_time": "08:00",
    "daily_news_topics": "বাংলাদেশ, প্রযুক্তি, বিশ্ব",
    "daily_news_last_run": "",
    "user_name": "",
    "max_history_messages": 30,
}


class Config:
    def __init__(self):
        self.path = app_dir() / "config.json"
        self.data = dict(DEFAULTS)
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:
                pass

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def voice_key(self) -> str:
        """Whisper-এর জন্য key: আলাদা দেওয়া না থাকলে, মূল প্রোভাইডার Groq হলে সেটাই।"""
        k = self.get("groq_key_for_voice")
        if not k and "groq.com" in self.get("base_url", ""):
            k = self.get("api_key")
        return k or ""
