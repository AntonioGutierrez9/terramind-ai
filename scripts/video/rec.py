"""Frame-accurate recorder for the TerraMind demo (Chrome screencast frames + markers + time-lapse cuts)."""
import base64
import json
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).parent
OVERLAY = (ROOT / "overlay.js").read_text(encoding="utf-8")


class Rec:
    def __init__(self, page):
        self.page = page
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._frame)
        self.active = False

    def _frame(self, p):
        if self.active:
            self.frames.append((time.time(), base64.b64decode(p["data"])))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]})
        except Exception:
            pass

    def start(self, name):
        self.name, self.frames, self.cuts, self.marks = name, [], [], {}
        self.active = True
        self.t0 = time.time()
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 93, "everyNthFrame": 1, "maxWidth": 1920, "maxHeight": 1080})
        self.page.wait_for_timeout(250)
        print(f"[rec] {name} started")

    def mark(self, key):
        self.marks[key] = time.time()

    @contextmanager
    def cut(self, keep=1.0, badge=True):
        """Time-lapse an AI wait: the interval is compressed to `keep` seconds in the edit."""
        a = time.time()
        if badge:
            self.page.evaluate("__tl(true)")
        try:
            yield
        finally:
            if badge:
                self.page.evaluate("__tl(false)")
            self.page.wait_for_timeout(350)
            self.cuts.append([a, time.time(), keep])

    def stop(self):
        self.page.wait_for_timeout(300)
        self.t1 = time.time()
        self.active = False
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:
            pass
        d = ROOT / "scenes" / self.name
        (d / "f").mkdir(parents=True, exist_ok=True)
        for old in (d / "f").glob("*.jpg"):
            old.unlink()
        times = []
        for i, (t, data) in enumerate(self.frames):
            (d / "f" / f"{i:05d}.jpg").write_bytes(data)
            times.append(t)
        json.dump({"t0": self.t0, "t1": self.t1, "times": times, "cuts": self.cuts, "marks": self.marks},
                  open(d / "meta.json", "w"), indent=1)
        print(f"[rec] {self.name}: {len(times)} frames, {self.t1 - self.t0:.1f}s raw, {len(self.cuts)} cuts")


# ---------------------------------------------------------------- demo actions
def center(loc):
    b = loc.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def move(page, loc, ms=620, dx=0, dy=0):
    x, y = center(loc)
    page.evaluate(f"__cur({x + dx},{y + dy})")
    page.wait_for_timeout(ms)


def click(page, loc, pause=350, scroll=True):
    if scroll:
        loc.scroll_into_view_if_needed()
    move(page, loc)
    x, y = center(loc)
    page.evaluate(f"__rip({x},{y})")
    loc.click()
    page.wait_for_timeout(pause)


def type_into(page, loc, text, delay=32):
    click(page, loc, pause=200)
    page.keyboard.type(text, delay=delay)


def zoom(page, loc, s=1.35, ms=1150):
    x, y = center(loc)
    page.evaluate(f"__zoom({s},{x},{y})")
    page.wait_for_timeout(ms)


def unzoom(page, ms=1050):
    page.evaluate("__zoom(1)")
    page.wait_for_timeout(ms)


def scroll_to(page, loc, block="start", ms=1100):
    loc.evaluate(f"e => e.scrollIntoView({{behavior: 'smooth', block: '{block}'}})")
    page.wait_for_timeout(ms)


def scroll_by(page, dy, ms=1100):
    page.evaluate(f"document.querySelector('.content').scrollBy({{top: {dy}, behavior: 'smooth'}})")
    page.wait_for_timeout(ms)


def cap(page, title, sub=""):
    page.evaluate("([t, s]) => __cap(t, s)", [title, sub])


def capoff(page):
    page.evaluate("__capOff()")
