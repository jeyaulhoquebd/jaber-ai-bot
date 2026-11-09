"""জাবেরের মস্তিষ্ক: OpenAI-compatible API (Groq / OpenRouter / Gemini / xAI / Ollama) + টুল কলিং লুপ।"""
import json
import threading

from openai import OpenAI

from .bridge import bridge
from .config import Config, app_dir
from .tools import TOOL_LABELS, TOOL_SPECS, run_tool

SYSTEM_PROMPT = """তুমি "জাবের" (Jaber) – ব্যবহারকারীর ব্যক্তিগত AI অ্যাসিস্ট্যান্ট, Windows কম্পিউটারে চলো।
{user_line}
নিয়ম:
- ব্যবহারকারী যে ভাষায় বলে সেই ভাষায় উত্তর দাও (সাধারণত বাংলা)। উত্তর ছোট, পরিষ্কার ও কাজের রাখো – উত্তরটা অনেক সময় জোরে পড়ে শোনানো হয়।
- তথ্য জানা না থাকলে বা সাম্প্রতিক হলে টুল দিয়ে খুঁজে নাও, বানিয়ে বলবে না। খবরের ক্ষেত্রে সূত্র (সাইটের নাম) উল্লেখ করো।
- লগইন লাগে এমন সাইটে (Facebook, Gmail ইত্যাদি) browser_open দিয়ে ঢুকবে। পেজ পড়ে element id দেখে ক্লিক/টাইপ করবে।
  লগইন না থাকলে ব্যবহারকারীকে বলবে জাবেরের ব্রাউজার উইন্ডোতে একবার নিজে লগইন করে নিতে।
- Facebook-এ পোস্ট: "What's on your mind"/"আপনি কী ভাবছেন" বক্সে ক্লিক → লেখা টাইপ → "Post"/"পোস্ট করুন" বাটন। পোস্ট/কমেন্ট/মেসেজ পাঠানোর আগে
  অ্যাপ নিজেই ব্যবহারকারীর অনুমতি চাইবে; অনুমতি না দিলে জোর করবে না।
- কখনো ব্যবহারকারীর অনুমতি ছাড়া অন্যের পোস্টে কমেন্ট, মেসেজ, বা স্প্যাম করবে না। পাসওয়ার্ড চাইবে না।
- আজ: {today}
"""


class Agent:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.history_file = app_dir() / "history.json"
        self.messages = self._load_history()
        self.lock = threading.Lock()
        self.stop_flag = False

    # ---------- ইতিহাস ----------
    def _load_history(self):
        try:
            return json.loads(self.history_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_history(self):
        try:
            self.history_file.write_text(json.dumps(self.messages[-200:], ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def clear(self):
        self.messages = []
        self._save_history()

    def _trimmed(self):
        """ফ্রি API-র টোকেন লিমিট বাঁচাতে শেষ কয়েকটা মেসেজ রাখে – সবসময় একটা user মেসেজ থেকে শুরু করে,
        যাতে tool call/result জোড়া ভেঙে না যায়।"""
        n = int(self.cfg.get("max_history_messages", 30))
        user_idx = [i for i, m in enumerate(self.messages) if m.get("role") == "user"]
        if not user_idx:
            return self.messages[-n:]
        start = max(0, len(self.messages) - n)
        # শুরুর জায়গা: start-এর পরের প্রথম user মেসেজ, কিন্তু চলতি প্রশ্নের পরে নয়
        later = [i for i in user_idx if i >= start]
        start = later[0] if later else user_idx[-1]
        msgs = self.messages[start:]
        # লম্বা টুল-চেইনে বড় রেজাল্ট ছোট করে পাঠাই
        out = []
        for m in msgs:
            if m.get("role") == "tool" and len(m.get("content", "")) > 3000 and m is not msgs[-1]:
                m = dict(m, content=m["content"][:3000] + "\n...[ছোট করা হয়েছে]")
            out.append(m)
        return out

    # ---------- ক্লায়েন্ট ----------
    def client(self):
        key = self.cfg.get("api_key") or "ollama"  # Ollama-তে key লাগে না
        base = self.cfg.get("base_url")
        if not base:
            raise RuntimeError("সেটিংসে API Base URL দেওয়া নেই।")
        return OpenAI(api_key=key, base_url=base, timeout=90, max_retries=2)

    def list_models(self):
        return sorted(m.id for m in self.client().models.list().data)

    def _system(self):
        import datetime as dt

        name = self.cfg.get("user_name")
        return SYSTEM_PROMPT.format(
            user_line=f"ব্যবহারকারীর নাম: {name}।" if name else "",
            today=dt.datetime.now().strftime("%Y-%m-%d %A %H:%M"),
        )

    # ---------- মূল লুপ ----------
    def ask(self, text: str, max_steps: int = 15, remember: bool = True) -> str:
        with self.lock:
            self.stop_flag = False
            convo = self.messages if remember else []
            convo.append({"role": "user", "content": text})
            client = self.client()
            model = self.cfg.get("model")
            final = ""
            for step in range(max_steps):
                if self.stop_flag:
                    final = "থামানো হয়েছে।"
                    break
                bridge.status("🤔 ভাবছি..." if step == 0 else "🤔 পরের ধাপ ভাবছি...")
                send = [{"role": "system", "content": self._system()}] + (self._trimmed() if remember else convo)
                try:
                    resp = client.chat.completions.create(
                        model=model, messages=send, tools=TOOL_SPECS, tool_choice="auto",
                        temperature=0.4, max_tokens=2048,
                    )
                except Exception as e:  # noqa: BLE001
                    err = str(e)
                    if "tool" in err.lower() and step == 0:
                        # কিছু মডেল টুল সাপোর্ট করে না – টুল ছাড়া আবার চেষ্টা
                        resp = client.chat.completions.create(model=model, messages=send, max_tokens=2048)
                    else:
                        raise
                msg = resp.choices[0].message
                calls = msg.tool_calls or []
                entry = {"role": "assistant", "content": msg.content or ""}
                if calls:
                    entry["tool_calls"] = [
                        {"id": c.id, "type": "function",
                         "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                        for c in calls
                    ]
                convo.append(entry)
                if not calls:
                    final = msg.content or ""
                    break
                for c in calls:
                    try:
                        args = json.loads(c.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    label = TOOL_LABELS.get(c.function.name, f"⚙️ {c.function.name}")
                    shown = args.get("query") or args.get("url") or args.get("task") or ""
                    bridge.status(f"{label}... {shown}"[:90])
                    bridge.log(f"{label}: {shown}", "tool")
                    result = run_tool(c.function.name, args)
                    convo.append({"role": "tool", "tool_call_id": c.id, "content": result})
            else:
                final = final or "অনেকগুলো ধাপ হয়ে গেছে, এখানেই থামলাম। আরও করতে বললে চালিয়ে যাব।"
                convo.append({"role": "assistant", "content": final})
            if remember:
                self._save_history()
            bridge.status("✅ প্রস্তুত")
            return final.strip()
