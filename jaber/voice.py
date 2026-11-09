"""ভয়েস: মাইক থেকে শোনা (Groq Whisper, বাংলা সাপোর্ট করে) আর কথা বলা (Microsoft Edge TTS, বাংলা কণ্ঠ)।"""
import asyncio
import io
import os
import re
import sys
import tempfile
import threading
import time
import wave

from .bridge import bridge
from .config import Config

RATE = 16000
CHUNK = 1024  # ~64ms


def _np():
    import numpy as np
    return np


# ---------------- রেকর্ডিং ----------------
class Mic:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.threshold = float(cfg.get("mic_threshold") or 0)

    def _stream(self):
        import sounddevice as sd
        return sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK)

    @staticmethod
    def _rms(block):
        np = _np()
        return float(np.sqrt(np.mean(block.astype(np.float32) ** 2)) + 1e-9)

    def calibrate(self, seconds=1.0):
        with self._stream() as s:
            vals = [self._rms(s.read(CHUNK)[0]) for _ in range(int(seconds * RATE / CHUNK))]
        noise = sorted(vals)[len(vals) // 2]
        self.threshold = max(noise * 3.0, 300.0)
        return self.threshold

    def record_utterance(self, max_seconds=15, start_timeout=6, silence_after=1.1, should_stop=None):
        """কথা শুরু হলে রেকর্ড শুরু, চুপ হলে শেষ। কিছু না বললে None।"""
        np = _np()
        if not self.threshold:
            self.calibrate()
        frames, started, silent_for, t0 = [], False, 0.0, time.time()
        block_sec = CHUNK / RATE
        pre = []  # কথা শুরুর ঠিক আগের অংশ, যাতে প্রথম শব্দ কেটে না যায়
        with self._stream() as s:
            while True:
                if should_stop is not None and should_stop():
                    return None
                block = s.read(CHUNK)[0].copy()
                loud = self._rms(block) > self.threshold
                if not started:
                    pre.append(block)
                    pre = pre[-5:]
                    if loud:
                        started = True
                        frames.extend(pre)
                    elif start_timeout and time.time() - t0 > start_timeout:
                        return None
                    continue
                frames.append(block)
                silent_for = 0.0 if loud else silent_for + block_sec
                if silent_for >= silence_after or len(frames) * block_sec >= max_seconds:
                    break
        audio = np.concatenate(frames)
        if len(audio) < RATE * 0.4:
            return None
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(audio.tobytes())
        return buf.getvalue()


def transcribe(cfg: Config, wav_bytes: bytes) -> str:
    from openai import OpenAI

    key = cfg.voice_key()
    if not key:
        raise RuntimeError("ভয়েসের জন্য Groq API key দরকার (ফ্রি)। সেটিংসে দিন।")
    client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", timeout=60)
    kw = dict(model=cfg.get("stt_model"), file=("speech.wav", wav_bytes), prompt="জাবের, Jaber")
    if cfg.get("stt_language"):
        kw["language"] = cfg.get("stt_language")
    res = client.audio.transcriptions.create(**kw)
    return (res.text or "").strip()


# ---------------- কথা বলা (TTS) ----------------
def _clean_for_speech(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*#`_>|\[\]]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:1500]


def _play_mp3_windows(path: str):
    import ctypes

    mci = ctypes.windll.winmm.mciSendStringW  # type: ignore[attr-defined]
    alias = f"jaber{int(time.time()*1000)}"
    mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
    mci(f"play {alias} wait", None, 0, None)
    mci(f"close {alias}", None, 0, None)


class Speaker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._lock = threading.Lock()
        self.speaking = False

    def say(self, text: str):
        if not self.cfg.get("tts_enabled") or not text:
            return
        threading.Thread(target=self._say, args=(text,), daemon=True).start()

    def say_blocking(self, text: str):
        if self.cfg.get("tts_enabled") and text:
            self._say(text)

    def _say(self, text):
        with self._lock:
            self.speaking = True
            try:
                import edge_tts

                path = os.path.join(tempfile.gettempdir(), f"jaber_tts_{os.getpid()}.mp3")

                async def run():
                    await edge_tts.Communicate(_clean_for_speech(text), self.cfg.get("tts_voice")).save(path)

                asyncio.run(run())
                if sys.platform == "win32":
                    _play_mp3_windows(path)
            except Exception as e:  # noqa: BLE001
                bridge.log(f"কথা বলতে সমস্যা: {e}", "warn")
            finally:
                self.speaking = False


# ---------------- "হেই জাবের" ওয়েক-ওয়ার্ড ----------------
def strip_wake_word(text: str, wake_words) -> tuple[bool, str]:
    """টেক্সটে জাবের নাম থাকলে (True, বাকি কমান্ড) ফেরত দেয়।"""
    low = text.lower()
    for w in wake_words:
        i = low.find(w.lower())
        if i != -1:
            rest = text[i + len(w):]
            rest = re.sub(r"^[\s,।.!?:;-]+", "", rest)
            return True, rest.strip()
    return False, ""


class WakeWordListener:
    """সবসময় শোনে; কথা শুনলে Whisper দিয়ে লেখা বানায়, তাতে 'জাবের' থাকলে কমান্ড হিসেবে নেয়।
    (ছোট ছোট অংশ পাঠায় – Groq ফ্রি লিমিটের মধ্যে থাকে।)"""

    def __init__(self, cfg: Config, mic: Mic, speaker: Speaker, on_command):
        self.cfg, self.mic, self.speaker, self.on_command = cfg, mic, speaker, on_command
        self.stop_event = threading.Event()
        self.paused = threading.Event()
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="jaber-wake")
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _loop(self):
        bridge.log("👂 'হেই জাবের' বললেই শুনব।", "info")
        while not self.stop_event.is_set():
            if self.paused.is_set() or self.speaker.speaking:
                time.sleep(0.3)
                continue
            try:
                # অন্য কাজ (🎤 বাটন, উত্তর দেওয়া) শুরু হলে সঙ্গে সঙ্গে মাইক ছেড়ে দেয়
                wav = self.mic.record_utterance(
                    max_seconds=10, start_timeout=0, silence_after=0.9,
                    should_stop=lambda: self.stop_event.is_set() or self.paused.is_set() or self.speaker.speaking)
                if not wav or self.speaker.speaking or self.paused.is_set():
                    continue
                text = transcribe(self.cfg, wav)
            except Exception as e:  # noqa: BLE001
                bridge.log(f"মাইক/ভয়েস সমস্যা: {e}", "warn")
                time.sleep(3)
                continue
            hit, command = strip_wake_word(text, self.cfg.get("wake_words"))
            if not hit:
                continue
            if not command:
                self.speaker.say_blocking("জি, বলুন।")
                try:
                    wav = self.mic.record_utterance(max_seconds=20, start_timeout=7)
                    command = transcribe(self.cfg, wav) if wav else ""
                except Exception as e:  # noqa: BLE001
                    bridge.log(f"ভয়েস সমস্যা: {e}", "warn")
                    command = ""
            if command:
                self.on_command(command)
