"""প্রতিদিনের খবর: নির্দিষ্ট সময়ে খবর খুঁজে বাংলায় সারাংশ বানায়, ফাইলে সেভ করে, শোনায়।"""
import datetime as dt
import threading
import time

from .bridge import bridge
from .config import Config, documents_dir

NEWS_PROMPT = """আজকের ({date}) গুরুত্বপূর্ণ খবর খুঁজে বের করো এই বিষয়গুলোতে: {topics}।
প্রতিটা বিষয়ের জন্য news_search টুল ব্যবহার করো (timelimit "d")। তারপর বাংলায় একটা রিপোর্ট লেখো:
1. "## আজকের শিরোনাম" – সবচেয়ে গুরুত্বপূর্ণ ৮-১০টা খবর, প্রতিটা ১-২ লাইনে, শেষে (সূত্র: সাইটের নাম, লিংক)।
2. "## ফেসবুক পোস্টের ড্রাফট" – এই খবরগুলো থেকে একটা সুন্দর, তথ্যভিত্তিক বাংলা ফেসবুক পোস্ট (ইমোজি ও ২-৩টা হ্যাশট্যাগসহ)।
3. "## শোনানোর জন্য সারাংশ" – ৩-৪ বাক্যে মুখে বলার মতো সংক্ষেপ।
কোনো খবর বানিয়ে লিখবে না, শুধু যা টুলে পেয়েছ।"""


def run_daily_news(agent, cfg: Config) -> tuple[str, str]:
    today = dt.date.today().isoformat()
    report = agent.ask(NEWS_PROMPT.format(date=today, topics=cfg.get("daily_news_topics")), remember=False, max_steps=12)
    folder = documents_dir() / "news"
    folder.mkdir(exist_ok=True)
    path = folder / f"{today}.md"
    path.write_text(f"# জাবেরের দৈনিক খবর – {today}\n\n{report}\n", encoding="utf-8")
    cfg.set("daily_news_last_run", today)
    cfg.save()
    return report, str(path)


def section(report: str, heading: str) -> str:
    """রিপোর্ট থেকে একটা ## সেকশনের লেখা বের করে।"""
    lines, out, on = report.splitlines(), [], False
    for ln in lines:
        if ln.strip().startswith("##"):
            on = heading in ln
            continue
        if on:
            out.append(ln)
    return "\n".join(out).strip()


class DailyScheduler:
    """অ্যাপ চালু থাকলে প্রতি মিনিটে চেক করে, সময় হলে একবার খবর আনে।"""

    def __init__(self, cfg: Config, on_due):
        self.cfg, self.on_due = cfg, on_due
        self._fired = ""
        threading.Thread(target=self._loop, daemon=True, name="jaber-daily").start()

    def _loop(self):
        time.sleep(20)
        while True:
            try:
                if self.cfg.get("daily_news_enabled"):
                    now = dt.datetime.now()
                    hh, mm = (int(x) for x in str(self.cfg.get("daily_news_time", "08:00")).split(":"))
                    due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                    today = now.date().isoformat()
                    if now >= due and self.cfg.get("daily_news_last_run") != today and self._fired != today:
                        # on_due False দিলে (অন্য কাজ চলছে) এক মিনিট পরে আবার চেষ্টা
                        if self.on_due() is not False:
                            self._fired = today
            except Exception as e:  # noqa: BLE001
                bridge.log(f"দৈনিক খবরের শিডিউলে সমস্যা: {e}", "warn")
            time.sleep(60)
