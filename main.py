"""জাবের – ব্যক্তিগত AI অ্যাসিস্ট্যান্ট।

চালানো:
    Jaber.exe                → চ্যাট উইন্ডো
    Jaber.exe --daily-news   → উইন্ডো ছাড়া শুধু আজকের খবর এনে Documents\\Jaber\\news-এ সেভ (Task Scheduler-এর জন্য)
"""
import sys


def main():
    # --windowed exe-তে কনসোল থাকে না; তখন লগ ফাইলে লিখি
    if sys.stdout is None or sys.stderr is None:
        from jaber.config import app_dir

        log = open(app_dir() / "jaber.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    if "--daily-news" in sys.argv:
        from jaber.agent import Agent
        from jaber.config import Config
        from jaber.daily import run_daily_news

        cfg = Config()
        _, path = run_daily_news(Agent(cfg), cfg)
        print(f"সেভ হয়েছে: {path}")
        return
    from jaber.gui import JaberApp

    JaberApp().run()


if __name__ == "__main__":
    main()
