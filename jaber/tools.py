"""জাবেরের টুলগুলো: AI মডেল যেগুলো কল করে কাজ করে।"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import webbrowser

import requests

from .bridge import bridge
from .config import app_dir, documents_dir

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JaberAssistant/1.0"}


# ---------------- ওয়েব ----------------
def _ddgs():
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS  # পুরোনো নাম
    return DDGS()


def web_search(query: str, max_results: int = 6) -> str:
    rows = list(_ddgs().text(query, max_results=max_results))
    if not rows:
        return "কিছু পাওয়া যায়নি।"
    return "\n\n".join(f"{i+1}. {r.get('title')}\n{r.get('href')}\n{r.get('body')}" for i, r in enumerate(rows))


def news_search(query: str, max_results: int = 8, timelimit: str = "d") -> str:
    rows = list(_ddgs().news(query, max_results=max_results, timelimit=timelimit))
    if not rows:
        return web_search(query + " news today", max_results)
    return "\n\n".join(
        f"{i+1}. {r.get('title')} ({r.get('source')}, {str(r.get('date',''))[:16]})\n{r.get('url')}\n{r.get('body')}"
        for i, r in enumerate(rows)
    )


def read_webpage(url: str, max_chars: int = 6000) -> str:
    from bs4 import BeautifulSoup

    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for t in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "form"]):
        t.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    text = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n")).strip()
    return f"{title}\n{url}\n\n{text[:max_chars]}"


def open_in_default_browser(url: str) -> str:
    webbrowser.open(url)
    return f"ডিফল্ট ব্রাউজারে খোলা হয়েছে: {url}"


# ---------------- কম্পিউটার ----------------
SAFE_APPS = {
    "notepad": "notepad", "নোটপ্যাড": "notepad",
    "calculator": "calc", "ক্যালকুলেটর": "calc",
    "explorer": "explorer", "file explorer": "explorer", "ফাইল": "explorer",
    "paint": "mspaint", "settings": "ms-settings:", "সেটিংস": "ms-settings:",
    "cmd": "cmd", "word": "winword", "excel": "excel", "chrome": "chrome", "edge": "msedge",
}


def open_app(name: str) -> str:
    key = name.strip().lower()
    target = SAFE_APPS.get(key)
    if not target:
        return f"'{name}' অ্যাপটা অনুমোদিত তালিকায় নেই। অনুমোদিত: {', '.join(sorted(set(SAFE_APPS)))}"
    if sys.platform != "win32":
        return "এই কাজটা শুধু Windows-এ চলে।"
    if target.endswith(":"):
        os.startfile(target)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)
    return f"{name} খোলা হয়েছে।"


def get_datetime() -> str:
    now = dt.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M (%A)")


# ---------------- কাজের লিস্ট ও নোট ----------------
TODO_FILE = app_dir() / "todos.json"


def _load_todos():
    try:
        return json.loads(TODO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_todos(items):
    TODO_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def todo_add(task: str, due: str = "") -> str:
    items = _load_todos()
    nid = max([i["id"] for i in items], default=0) + 1
    items.append({"id": nid, "task": task, "due": due, "done": False, "created": get_datetime()})
    _save_todos(items)
    return f"কাজ যোগ হয়েছে (#{nid}): {task}"


def todo_list(include_done: bool = False) -> str:
    items = [i for i in _load_todos() if include_done or not i["done"]]
    if not items:
        return "কোনো বাকি কাজ নেই।"
    return "\n".join(f"#{i['id']} {'✅' if i['done'] else '⬜'} {i['task']}" + (f" (শেষ সময়: {i['due']})" if i["due"] else "") for i in items)


def todo_done(task_id: int) -> str:
    items = _load_todos()
    for i in items:
        if i["id"] == int(task_id):
            i["done"] = True
            _save_todos(items)
            return f"#{task_id} শেষ হিসেবে চিহ্নিত হয়েছে।"
    return f"#{task_id} পাওয়া যায়নি।"


def save_note(title: str, content: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]+', "_", title).strip() or "note"
    folder = documents_dir() / "notes"
    folder.mkdir(exist_ok=True)
    path = folder / f"{dt.date.today()}_{safe}.md"
    path.write_text(content, encoding="utf-8")
    return f"নোট সেভ হয়েছে: {path}"


# ---------------- ব্রাউজার (Playwright) ----------------
def _b():
    from .browser import browser
    return browser


def browser_open(url: str) -> str:
    return _b().open(url)


def browser_read() -> str:
    return _b().read()


def browser_click(element_id: int) -> str:
    return _b().click(element_id)


def browser_type(element_id: int, text: str, press_enter: bool = False) -> str:
    return _b().type(element_id, text, press_enter)


def browser_scroll(direction: str = "down") -> str:
    return _b().scroll(direction)


def browser_back() -> str:
    return _b().back()


# ---------------- Google Drive ----------------
def drive_search(query: str = "") -> str:
    from . import gdrive
    return gdrive.search(query)


def drive_read(file_id: str) -> str:
    from . import gdrive
    return gdrive.read(file_id)


def drive_upload_text(name: str, content: str) -> str:
    from . import gdrive
    if not bridge.confirm(f"জাবের Google Drive-এ '{name}' ফাইল সেভ করতে চায়। অনুমতি দেবেন?"):
        return "ব্যবহারকারী অনুমতি দেননি।"
    return gdrive.upload_text(name, content)


# ---------------- টুল স্কিমা ----------------
def _fn(name, desc, props=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []},
        },
    }


S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}

TOOL_SPECS = [
    _fn("web_search", "ইন্টারনেটে সার্চ করে (DuckDuckGo)। সাধারণ প্রশ্ন, তথ্য খোঁজার জন্য।", {"query": S}, ["query"]),
    _fn("news_search", "সাম্প্রতিক খবর খোঁজে। timelimit: d=আজ, w=এই সপ্তাহ, m=এই মাস।",
        {"query": S, "timelimit": {"type": "string", "enum": ["d", "w", "m"]}}, ["query"]),
    _fn("read_webpage", "একটা ওয়েবপেজের লেখা পড়ে আনে (লগইন ছাড়া পাবলিক পেজ)।", {"url": S}, ["url"]),
    _fn("open_in_default_browser", "ব্যবহারকারীর ডিফল্ট ব্রাউজারে একটা লিংক খোলে, শুধু দেখানোর জন্য।", {"url": S}, ["url"]),
    _fn("open_app", "কম্পিউটারের একটা অ্যাপ খোলে (notepad, calculator, explorer, settings, word, excel, chrome, edge)।", {"name": S}, ["name"]),
    _fn("get_datetime", "এখনকার তারিখ ও সময়।"),
    _fn("todo_add", "ব্যবহারকারীর কাজের লিস্টে নতুন কাজ যোগ করে।", {"task": S, "due": S}, ["task"]),
    _fn("todo_list", "আজকের/বাকি কাজের লিস্ট দেখায়।", {"include_done": B}),
    _fn("todo_done", "একটা কাজ শেষ হিসেবে চিহ্নিত করে।", {"task_id": I}, ["task_id"]),
    _fn("save_note", "লেখা/রিপোর্ট কম্পিউটারের Documents\\Jaber\\notes ফোল্ডারে সেভ করে।", {"title": S, "content": S}, ["title", "content"]),
    _fn("browser_open", "জাবেরের নিজস্ব ব্রাউজারে (ব্যবহারকারীর লগইন করা প্রোফাইল) একটা URL খোলে এবং পেজের লেখা ও ক্লিকযোগ্য এলিমেন্টের id লিস্ট ফেরত দেয়। Facebook, Gmail ইত্যাদি লগইন লাগে এমন সাইটের জন্য এটা ব্যবহার করো।", {"url": S}, ["url"]),
    _fn("browser_read", "বর্তমান ব্রাউজার পেজ আবার পড়ে, নতুন element id সহ।"),
    _fn("browser_click", "browser_open/browser_read থেকে পাওয়া id-ওয়ালা এলিমেন্টে ক্লিক করে।", {"element_id": I}, ["element_id"]),
    _fn("browser_type", "একটা টেক্সট বক্সে লেখে। press_enter=true দিলে Enter চাপে (কমেন্ট পাঠাতে)।", {"element_id": I, "text": S, "press_enter": B}, ["element_id", "text"]),
    _fn("browser_scroll", "পেজ উপরে/নিচে স্ক্রল করে।", {"direction": {"type": "string", "enum": ["down", "up"]}}),
    _fn("browser_back", "ব্রাউজারে আগের পেজে ফিরে যায়।"),
    _fn("drive_search", "ব্যবহারকারীর Google Drive-এ নাম দিয়ে ফাইল খোঁজে (খালি query = সাম্প্রতিক ফাইল)।", {"query": S}),
    _fn("drive_read", "Google Drive-এর একটা ফাইল (Docs/Sheets/টেক্সট) পড়ে।", {"file_id": S}, ["file_id"]),
    _fn("drive_upload_text", "Google Drive-এ একটা টেক্সট ফাইল সেভ করে।", {"name": S, "content": S}, ["name", "content"]),
]

TOOL_FUNCS = {
    "web_search": web_search, "news_search": news_search, "read_webpage": read_webpage,
    "open_in_default_browser": open_in_default_browser, "open_app": open_app, "get_datetime": get_datetime,
    "todo_add": todo_add, "todo_list": todo_list, "todo_done": todo_done, "save_note": save_note,
    "browser_open": browser_open, "browser_read": browser_read, "browser_click": browser_click,
    "browser_type": browser_type, "browser_scroll": browser_scroll, "browser_back": browser_back,
    "drive_search": drive_search, "drive_read": drive_read, "drive_upload_text": drive_upload_text,
}

TOOL_LABELS = {
    "web_search": "🔍 সার্চ করছি", "news_search": "📰 খবর খুঁজছি", "read_webpage": "📄 পেজ পড়ছি",
    "browser_open": "🌐 ব্রাউজারে খুলছি", "browser_read": "🌐 পেজ দেখছি", "browser_click": "🖱️ ক্লিক করছি",
    "browser_type": "⌨️ লিখছি", "browser_scroll": "🌐 স্ক্রল করছি", "drive_search": "📁 Drive-এ খুঁজছি",
    "drive_read": "📁 Drive ফাইল পড়ছি", "drive_upload_text": "📁 Drive-এ সেভ করছি",
}


def run_tool(name: str, args: dict, max_chars: int = 7000) -> str:
    fn = TOOL_FUNCS.get(name)
    if not fn:
        return f"Error: '{name}' নামে কোনো টুল নেই।"
    try:
        out = fn(**(args or {}))
    except TypeError as e:
        return f"Error: ভুল প্যারামিটার: {e}"
    except Exception as e:  # noqa: BLE001
        return f"Error: {type(e).__name__}: {e}"
    out = str(out)
    return out if len(out) <= max_chars else out[:max_chars] + "\n...[বাকিটা কেটে দেওয়া হয়েছে]"
