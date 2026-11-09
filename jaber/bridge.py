"""ব্যাকগ্রাউন্ড থ্রেড থেকে UI-তে মেসেজ/কনফার্মেশন পাঠানোর সেতু।
GUI না থাকলে (যেমন --daily-news মোডে) কনসোলে প্রিন্ট করে এবং ঝুঁকিপূর্ণ কাজ বাতিল করে।"""
import threading


class Bridge:
    def __init__(self):
        self.on_log = lambda text, kind="info": print(f"[{kind}] {text}")
        self.on_status = lambda text: None
        self._confirm_impl = None  # GUI সেট করবে: fn(question) -> bool

    def log(self, text, kind="info"):
        try:
            self.on_log(text, kind)
        except Exception:
            print(text)

    def status(self, text):
        try:
            self.on_status(text)
        except Exception:
            pass

    def confirm(self, question: str) -> bool:
        """ব্যবহারকারীর অনুমতি চায়। GUI না থাকলে নিরাপত্তার জন্য 'না' ধরে নেয়।"""
        if self._confirm_impl is None:
            self.log(f"অনুমতি দরকার ছিল কিন্তু GUI নেই, বাতিল: {question}", "warn")
            return False
        return bool(self._confirm_impl(question))


bridge = Bridge()


class Future:
    def __init__(self):
        self._ev = threading.Event()
        self.result = None
        self.error = None

    def set(self, result=None, error=None):
        self.result, self.error = result, error
        self._ev.set()

    def wait(self, timeout=None):
        if not self._ev.wait(timeout):
            raise TimeoutError("সময় শেষ")
        if self.error:
            raise self.error
        return self.result
