"""জাবেরের চ্যাট উইন্ডো (tkinter – Windows-এ আলাদা কিছু ইনস্টল লাগে না)।"""
import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from .agent import Agent
from .bridge import Future, bridge
from .config import PROVIDERS, Config
from .daily import DailyScheduler, run_daily_news, section
from .voice import Mic, Speaker, WakeWordListener, transcribe

FONT = ("Nirmala UI", 11)  # Windows-এর বাংলা ফন্ট
BG, PANEL, FG, ACCENT, MUTED = "#0f172a", "#1e293b", "#e2e8f0", "#38bdf8", "#94a3b8"


class JaberApp:
    def __init__(self):
        self.cfg = Config()
        self.agent = Agent(self.cfg)
        self.mic = Mic(self.cfg)
        self.speaker = Speaker(self.cfg)
        self.ui_q = queue.Queue()
        self.busy = False
        self.wake = None

        self.root = tk.Tk()
        self.root.title("জাবের – আপনার AI অ্যাসিস্ট্যান্ট")
        self.root.geometry("760x680")
        self.root.configure(bg=BG)
        self._build()

        bridge.on_log = lambda t, k="info": self.ui_q.put(("log", t, k))
        bridge.on_status = lambda t: self.ui_q.put(("status", t))
        bridge._confirm_impl = self._confirm_from_thread
        self.root.after(80, self._pump)

        DailyScheduler(self.cfg, lambda: self._run_bg(self._daily_job))
        if self.cfg.get("wake_word_enabled"):
            self.wake_var.set(True)
            self._toggle_wake()

        if not self.cfg.get("api_key") and "localhost" not in self.cfg.get("base_url", ""):
            self._add("জাবের", "আসসালামু আলাইকুম! আমি জাবের। শুরু করতে ⚙ সেটিংসে গিয়ে আপনার ফ্রি Groq API key দিন "
                               "(console.groq.com থেকে পাবেন)।", "bot")
            self.root.after(600, self.open_settings)
        else:
            self._add("জাবের", "আসসালামু আলাইকুম! আমি জাবের। লিখুন, 🎤 চাপুন, অথবা 'হেই জাবের' বলুন।", "bot")

    # ---------------- UI তৈরি ----------------
    def _build(self):
        top = tk.Frame(self.root, bg=PANEL)
        top.pack(fill="x")
        tk.Label(top, text="🤖 জাবের", font=("Nirmala UI", 16, "bold"), bg=PANEL, fg=ACCENT).pack(side="left", padx=12, pady=8)
        self.status = tk.Label(top, text="✅ প্রস্তুত", font=("Nirmala UI", 10), bg=PANEL, fg=MUTED)
        self.status.pack(side="left", padx=8)
        for txt, cmd in (("⚙ সেটিংস", self.open_settings), ("🗑 নতুন চ্যাট", self._clear),
                         ("📰 আজকের খবর", lambda: self._run_bg(self._daily_job))):
            tk.Button(top, text=txt, command=cmd, font=("Nirmala UI", 10), bg=BG, fg=FG, relief="flat",
                      activebackground=ACCENT, padx=8).pack(side="right", padx=4, pady=6)

        self.chat = scrolledtext.ScrolledText(self.root, wrap="word", font=FONT, bg=BG, fg=FG, relief="flat",
                                              insertbackground=FG, padx=12, pady=10, state="disabled")
        self.chat.pack(fill="both", expand=True)
        self.chat.tag_config("me_name", foreground="#fbbf24", font=("Nirmala UI", 10, "bold"))
        self.chat.tag_config("bot_name", foreground=ACCENT, font=("Nirmala UI", 10, "bold"))
        self.chat.tag_config("tool", foreground=MUTED, font=("Nirmala UI", 9, "italic"))
        self.chat.tag_config("warn", foreground="#f87171", font=("Nirmala UI", 10))
        self.chat.tag_config("body", spacing3=8)

        bottom = tk.Frame(self.root, bg=PANEL)
        bottom.pack(fill="x")
        self.wake_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bottom, text="👂 হেই জাবের", variable=self.wake_var, command=self._toggle_wake,
                       bg=PANEL, fg=FG, selectcolor=BG, activebackground=PANEL, font=("Nirmala UI", 10)).pack(side="left", padx=6)
        self.entry = tk.Text(bottom, height=2, font=FONT, bg=BG, fg=FG, insertbackground=FG, relief="flat", wrap="word")
        self.entry.pack(side="left", fill="x", expand=True, padx=6, pady=8)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Control-space>", lambda e: (self._mic_click(), "break")[1])
        self.mic_btn = tk.Button(bottom, text="🎤", command=self._mic_click, font=("Segoe UI Emoji", 14), bg=BG, fg=FG,
                                 relief="flat", width=3)
        self.mic_btn.pack(side="left", padx=2)
        tk.Button(bottom, text="⏹", command=self._stop, font=("Segoe UI Emoji", 12), bg=BG, fg=FG, relief="flat",
                  width=3).pack(side="left", padx=2)
        tk.Button(bottom, text="পাঠান ➤", command=self._send, font=("Nirmala UI", 11, "bold"), bg=ACCENT, fg=BG,
                  relief="flat", padx=10).pack(side="left", padx=6)
        self.entry.focus_set()

    # ---------------- থ্রেড-নিরাপদ UI আপডেট ----------------
    def _pump(self):
        try:
            while True:
                item = self.ui_q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._add(None, item[1], item[2])
                elif kind == "status":
                    self.status.config(text=item[1])
                elif kind == "msg":
                    self._add(item[1], item[2], item[3])
                elif kind == "confirm":
                    _, question, fut = item
                    fut.set(result=messagebox.askyesno("জাবের অনুমতি চাইছে", question, parent=self.root))
                elif kind == "call":
                    item[1]()
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _confirm_from_thread(self, question):
        if threading.current_thread() is threading.main_thread():
            return messagebox.askyesno("জাবের অনুমতি চাইছে", question, parent=self.root)
        fut = Future()
        self.ui_q.put(("confirm", question, fut))
        return fut.wait(timeout=600)

    def _add(self, who, text, kind="bot"):
        self.chat.config(state="normal")
        if kind in ("tool", "info"):
            self.chat.insert("end", f"  {text}\n", "tool")
        elif kind == "warn":
            self.chat.insert("end", f"⚠ {text}\n", "warn")
        else:
            self.chat.insert("end", f"{who}\n", "me_name" if kind == "me" else "bot_name")
            self.chat.insert("end", f"{text}\n\n", "body")
        self.chat.config(state="disabled")
        self.chat.see("end")

    # ---------------- কাজ চালানো ----------------
    def _run_bg(self, fn, *args):
        def wrap():
            try:
                fn(*args)
            except Exception as e:  # noqa: BLE001
                self.ui_q.put(("log", f"সমস্যা হয়েছে: {e}", "warn"))
                self.ui_q.put(("status", "⚠ সমস্যা"))
            finally:
                self.busy = False
                if self.wake:
                    self.wake.paused.clear()
        if self.busy:
            self.ui_q.put(("log", "আগের কাজটা চলছে, একটু অপেক্ষা করুন (বা ⏹ চাপুন)।", "warn"))
            return False
        self.busy = True
        if self.wake:
            self.wake.paused.set()
        threading.Thread(target=wrap, daemon=True).start()
        return True

    def _handle(self, text, spoken=False):
        self.ui_q.put(("msg", "আপনি" + (" 🎤" if spoken else ""), text, "me"))
        answer = self.agent.ask(text)
        self.ui_q.put(("msg", "জাবের", answer or "(কোনো উত্তর আসেনি)", "bot"))
        self.speaker.say_blocking(answer) if spoken else self.speaker.say(answer)

    def _on_enter(self, e):
        if e.state & 0x1:  # Shift+Enter = নতুন লাইন
            return None
        self._send()
        return "break"

    def _send(self):
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        self._run_bg(self._handle, text)

    def _stop(self):
        self.agent.stop_flag = True
        self.status.config(text="⏹ থামানো হচ্ছে...")

    def _clear(self):
        self.agent.clear()
        self.chat.config(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.config(state="disabled")
        self._add("জাবের", "নতুন করে শুরু করলাম। বলুন কী করতে পারি?", "bot")

    def _mic_click(self):
        def job():
            self.ui_q.put(("status", "🎤 শুনছি... কথা বলুন"))
            self.ui_q.put(("call", lambda: self.mic_btn.config(bg="#dc2626")))
            try:
                wav = self.mic.record_utterance(max_seconds=25, start_timeout=8)
            finally:
                self.ui_q.put(("call", lambda: self.mic_btn.config(bg=BG)))
            if not wav:
                self.ui_q.put(("status", "কিছু শুনতে পাইনি"))
                return
            self.ui_q.put(("status", "📝 লিখছি..."))
            text = transcribe(self.cfg, wav)
            if text:
                self._handle(text, spoken=True)
            else:
                self.ui_q.put(("status", "বুঝতে পারিনি, আবার বলুন"))
        self._run_bg(job)

    def _toggle_wake(self):
        on = self.wake_var.get()
        self.cfg.set("wake_word_enabled", on)
        self.cfg.save()
        if on:
            if not self.cfg.voice_key():
                self._add(None, "ভয়েসের জন্য সেটিংসে Groq API key দিন।", "warn")
                self.wake_var.set(False)
                return
            self.wake = WakeWordListener(self.cfg, self.mic, self.speaker,
                                         lambda cmd: self._run_bg(self._handle, cmd, True))
            self.wake.start()
        elif self.wake:
            self.wake.stop()
            self.wake = None
            self._add(None, "👂 শোনা বন্ধ।", "info")

    # ---------------- দৈনিক খবর ----------------
    def _daily_job(self):
        self.ui_q.put(("log", "📰 আজকের খবর খুঁজছি...", "info"))
        report, path = run_daily_news(self.agent, self.cfg)
        self.ui_q.put(("msg", "জাবের – আজকের খবর", report + f"\n\n💾 সেভ হয়েছে: {path}", "bot"))
        spoken = section(report, "শোনানোর") or "আজকের খবর তৈরি, স্ক্রিনে দেখুন।"
        self.speaker.say_blocking(spoken)
        post = section(report, "ফেসবুক")
        if post and self._confirm_from_thread(f"এই পোস্টটা কি Facebook-এ দেব?\n\n{post[:900]}"):
            answer = self.agent.ask(
                "নিচের লেখাটা হুবহু আমার Facebook-এ পোস্ট করো। browser_open দিয়ে https://www.facebook.com খোলো, "
                "পোস্ট লেখার বক্সে ক্লিক করো, লেখাটা টাইপ করো, তারপর Post বাটনে ক্লিক করো।\n\n---\n" + post
            )
            self.ui_q.put(("msg", "জাবের", answer, "bot"))

    # ---------------- সেটিংস ----------------
    def open_settings(self):
        SettingsDialog(self)

    def run(self):
        self.root.mainloop()


class SettingsDialog:
    def __init__(self, app: JaberApp):
        self.app, cfg = app, app.cfg
        w = self.w = tk.Toplevel(app.root)
        w.title("জাবের – সেটিংস")
        w.geometry("620x640")
        w.transient(app.root)
        frm = ttk.Frame(w, padding=14)
        frm.pack(fill="both", expand=True)
        self.vars = {}
        row = 0

        def label(text):
            nonlocal row
            ttk.Label(frm, text=text, font=("Nirmala UI", 10)).grid(row=row, column=0, sticky="w", pady=4)

        def entry(key, text, show=None):
            nonlocal row
            label(text)
            v = tk.StringVar(value=str(cfg.get(key) or ""))
            ttk.Entry(frm, textvariable=v, width=52, show=show).grid(row=row, column=1, columnspan=2, sticky="we", pady=4)
            self.vars[key] = v
            row += 1

        label("AI প্রোভাইডার")
        self.provider = tk.StringVar(value=cfg.get("provider"))
        cb = ttk.Combobox(frm, textvariable=self.provider, values=list(PROVIDERS), state="readonly", width=40)
        cb.grid(row=row, column=1, columnspan=2, sticky="we")
        cb.bind("<<ComboboxSelected>>", self._provider_changed)
        row += 1
        entry("base_url", "API Base URL")
        entry("api_key", "API Key", show="•")
        label("মডেল")
        self.model = tk.StringVar(value=cfg.get("model"))
        self.model_cb = ttk.Combobox(frm, textvariable=self.model, width=36)
        self.model_cb.grid(row=row, column=1, sticky="we")
        ttk.Button(frm, text="মডেল লোড", command=self._load_models).grid(row=row, column=2, padx=4)
        row += 1
        entry("groq_key_for_voice", "ভয়েসের Groq key (প্রোভাইডার Groq হলে খালি রাখুন)", show="•")
        entry("stt_language", "শোনার ভাষা (খালি=অটো, bn=বাংলা)")
        label("জাবেরের কণ্ঠ")
        self.voice = tk.StringVar(value=cfg.get("tts_voice"))
        ttk.Combobox(frm, textvariable=self.voice, width=40, values=[
            "bn-BD-NabanitaNeural", "bn-BD-PradeepNeural", "bn-IN-TanishaaNeural", "bn-IN-BashkarNeural",
            "en-US-GuyNeural", "en-US-JennyNeural"]).grid(row=row, column=1, columnspan=2, sticky="we")
        row += 1
        self.tts = tk.BooleanVar(value=cfg.get("tts_enabled"))
        ttk.Checkbutton(frm, text="উত্তর মুখে বলে শোনাবে", variable=self.tts).grid(row=row, column=1, sticky="w")
        row += 1
        entry("user_name", "আপনার নাম")
        ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="we", pady=8)
        row += 1
        self.daily = tk.BooleanVar(value=cfg.get("daily_news_enabled"))
        ttk.Checkbutton(frm, text="প্রতিদিন খবর আনবে", variable=self.daily).grid(row=row, column=1, sticky="w")
        row += 1
        entry("daily_news_time", "খবরের সময় (24 ঘণ্টা, যেমন 08:00)")
        entry("daily_news_topics", "খবরের বিষয় (কমা দিয়ে)")
        frm.columnconfigure(1, weight=1)
        ttk.Button(frm, text="💾 সেভ করুন", command=self._save).grid(row=row, column=1, sticky="e", pady=16)
        ttk.Label(frm, text="ফ্রি Groq key: console.groq.com → API Keys\nGoogle Drive: README দেখুন",
                  foreground="#64748b").grid(row=row + 1, column=0, columnspan=3, sticky="w")

    def _provider_changed(self, _=None):
        p = PROVIDERS[self.provider.get()]
        if p["base_url"]:
            self.vars["base_url"].set(p["base_url"])
        if p["model"]:
            self.model.set(p["model"])

    def _apply(self):
        cfg = self.app.cfg
        cfg.set("provider", self.provider.get())
        for k, v in self.vars.items():
            cfg.set(k, v.get().strip())
        cfg.set("model", self.model.get().strip())
        cfg.set("tts_voice", self.voice.get().strip())
        cfg.set("tts_enabled", self.tts.get())
        cfg.set("daily_news_enabled", self.daily.get())

    def _load_models(self):
        self._apply()

        def job():
            try:
                models = self.app.agent.list_models()
                self.app.ui_q.put(("call", lambda: self.model_cb.config(values=models)))
                self.app.ui_q.put(("log", f"{len(models)}টা মডেল পাওয়া গেছে – লিস্ট থেকে বেছে নিন।", "info"))
            except Exception as e:  # noqa: BLE001
                self.app.ui_q.put(("log", f"মডেল লোড হয়নি (key ঠিক আছে?): {e}", "warn"))
        threading.Thread(target=job, daemon=True).start()

    def _save(self):
        self._apply()
        self.app.cfg.save()
        self.app._add(None, "✅ সেটিংস সেভ হয়েছে।", "info")
        self.w.destroy()
