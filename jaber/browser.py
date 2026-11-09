"""Playwright দিয়ে ব্রাউজার কন্ট্রোল।
- Windows-এ আগে থেকে থাকা Microsoft Edge (বা Chrome) ব্যবহার করে, আলাদা ব্রাউজার ডাউনলোড লাগে না।
- আলাদা প্রোফাইল (%APPDATA%\\Jaber\\browser_profile) – প্রথমবার নিজে Facebook/Gmail-এ লগইন করবেন,
  পরে সেটা মনে থাকবে।
- Playwright-এর sync API একটাই থ্রেড থেকে চালাতে হয়, তাই সব কাজ একটা ডেডিকেটেড থ্রেডে কিউ করে চলে।
"""
import queue
import re
import threading

from .bridge import Future, bridge
from .config import app_dir

# এসব শব্দওয়ালা বাটনে ক্লিক করার আগে অবশ্যই আপনার অনুমতি নেবে
RISKY_WORDS = re.compile(
    r"post|publish|comment|reply|send|share|submit|delete|remove|buy|pay|order|confirm|"
    r"পোস্ট|প্রকাশ|মন্তব্য|কমেন্ট|উত্তর|পাঠান|পাঠাও|শেয়ার|জমা|মুছ|কিনুন|পেমেন্ট|নিশ্চিত",
    re.I,
)

_MARK_JS = r"""
() => {
  document.querySelectorAll('[data-jaber-id]').forEach(e => e.removeAttribute('data-jaber-id'));
  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, [role=button], [role=link], [role=textbox], [contenteditable=true], [role=menuitem], [role=tab]';
  const out = [];
  let id = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (r.bottom < 0 || r.top > window.innerHeight * 2) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none') continue;
    let label = (el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder ||
                 el.getAttribute('title') || el.getAttribute('aria-placeholder') || '').trim().replace(/\s+/g, ' ');
    if (!label && el.tagName === 'A') label = el.getAttribute('href') || '';
    if (!label) continue;
    id++;
    el.setAttribute('data-jaber-id', String(id));
    const kind = el.isContentEditable || el.getAttribute('role') === 'textbox' ? 'textbox' : el.tagName.toLowerCase();
    out.push(`[${id}] ${kind}: ${label.slice(0, 80)}`);
    if (id >= 80) break;
  }
  return out;
}
"""


class BrowserWorker:
    def __init__(self):
        self._q = queue.Queue()
        self._thread = None
        self._ctx = None
        self._page = None
        self._pw = None
        self._labels = {}

    # ---------- থ্রেড ম্যানেজমেন্ট ----------
    def _ensure_thread(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="jaber-browser")
        self._thread.start()

    def _loop(self):
        while True:
            fn, args, fut = self._q.get()
            try:
                fut.set(result=fn(*args))
            except Exception as e:  # noqa: BLE001
                fut.set(error=e)

    def call(self, fn, *args, timeout=120):
        self._ensure_thread()
        fut = Future()
        self._q.put((fn, args, fut))
        return fut.wait(timeout)

    # ---------- ব্রাউজার চালু ----------
    def _launch(self):
        if self._page is not None:
            try:
                self._page.title()
                return self._page
            except Exception:
                self._page = None
        if self._pw is None:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
        if self._ctx is None:
            profile = str(app_dir() / "browser_profile")
            last_err = None
            for channel in ("msedge", "chrome", None):
                try:
                    kw = dict(user_data_dir=profile, headless=False, viewport=None,
                              args=["--start-maximized"])
                    if channel:
                        kw["channel"] = channel
                    self._ctx = self._pw.chromium.launch_persistent_context(**kw)
                    break
                except Exception as e:  # noqa: BLE001
                    last_err = e
            if self._ctx is None:
                raise RuntimeError(f"ব্রাউজার চালু করা গেল না (Edge/Chrome ইনস্টল আছে?): {last_err}")
            self._ctx.on("close", lambda *_: self._reset())
        pages = self._ctx.pages
        self._page = pages[0] if pages else self._ctx.new_page()
        return self._page

    def _reset(self):
        self._ctx = None
        self._page = None

    # ---------- টুল ফাংশন (ব্রাউজার থ্রেডে চলে) ----------
    def _snapshot(self, max_chars=5000):
        page = self._page
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        elements = page.evaluate(_MARK_JS)
        self._labels = {}
        for line in elements:
            m = re.match(r"\[(\d+)\] [^:]+: (.*)", line)
            if m:
                self._labels[m.group(1)] = m.group(2)
        try:
            text = page.inner_text("body", timeout=5000)
        except Exception:
            text = ""
        text = re.sub(r"\n\s*\n+", "\n", text).strip()[:max_chars]
        return (f"URL: {page.url}\nশিরোনাম: {page.title()}\n\n--- পেজের লেখা ---\n{text}\n\n"
                f"--- ক্লিক/টাইপ করার মতো এলিমেন্ট (id দিয়ে ব্যবহার করুন) ---\n" + "\n".join(elements))

    def _open(self, url):
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url):
            url = "https://" + url
        page = self._launch()
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        return self._snapshot()

    def _read(self):
        self._launch()
        return self._snapshot()

    def _el(self, el_id):
        loc = self._page.locator(f'[data-jaber-id="{el_id}"]')
        if loc.count() == 0:
            raise ValueError(f"id {el_id} পাওয়া যায়নি। আগে browser_read চালিয়ে নতুন id নিন।")
        return loc.first

    def _click(self, el_id):
        self._launch()
        label = self._labels.get(str(el_id), "")
        if RISKY_WORDS.search(label) and not bridge.confirm(f"জাবের এই বাটনে ক্লিক করতে চায়:\n\n“{label}”\n\nঅনুমতি দেবেন?"):
            return "ব্যবহারকারী অনুমতি দেননি। ক্লিক করা হয়নি।"
        self._el(el_id).click(timeout=10000)
        self._page.wait_for_timeout(2000)
        return "ক্লিক হয়েছে।\n\n" + self._snapshot(3000)

    def _type(self, el_id, text, press_enter):
        self._launch()
        if press_enter and not bridge.confirm(
            f"জাবের এই লেখা টাইপ করে Enter চাপতে চায় (এতে পোস্ট/কমেন্ট/মেসেজ চলে যেতে পারে):\n\n{text[:600]}\n\nঅনুমতি দেবেন?"
        ):
            return "ব্যবহারকারী অনুমতি দেননি।"
        el = self._el(el_id)
        el.click(timeout=10000)
        try:
            el.fill(text, timeout=5000)
        except Exception:
            # Facebook-এর মতো contenteditable বক্সে fill কাজ করে না
            self._page.keyboard.type(text, delay=15)
        if press_enter:
            self._page.keyboard.press("Enter")
        self._page.wait_for_timeout(1500)
        return "টাইপ হয়েছে।\n\n" + self._snapshot(2000)

    def _scroll(self, direction):
        self._launch()
        self._page.mouse.wheel(0, 900 if direction != "up" else -900)
        self._page.wait_for_timeout(1500)
        return self._snapshot()

    def _back(self):
        self._launch()
        self._page.go_back(timeout=20000)
        self._page.wait_for_timeout(1500)
        return self._snapshot()

    # ---------- পাবলিক API ----------
    def open(self, url):
        return self.call(self._open, url)

    def read(self):
        return self.call(self._read)

    def click(self, el_id):
        return self.call(self._click, el_id, timeout=600)

    def type(self, el_id, text, press_enter=False):
        return self.call(self._type, el_id, text, press_enter, timeout=600)

    def scroll(self, direction="down"):
        return self.call(self._scroll, direction)

    def back(self):
        return self.call(self._back)


browser = BrowserWorker()
