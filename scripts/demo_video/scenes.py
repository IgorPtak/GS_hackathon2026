"""The demo scenes, as scripted clicks. Each scene is one silent clip (see docs/demo.md)."""

from __future__ import annotations

import asyncio
import hashlib
import re
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path

from playwright.async_api import BrowserContext, Page
from recorder import MIN_ZOOM_SECONDS, TEMPO, Recorder

BASE = "http://localhost:5173"
RUNBOOK_TEXT = (
    "When a payment is declined, first check the payment gateway health. If the gateway is fine, "
    "retry the payment once. If it is declined again, escalate to the payments on-call lead, which "
    "needs approval. Afterwards tell the customer support team."
)

Scene = Callable[[Recorder], Awaitable[None]]


async def sign_in_as(page: Page, person: str, team: str, path: str = "/home") -> None:
    """Signed in, welcome already seen: the state between scenes, set off-camera."""
    await page.goto(f"{BASE}{path}?person={person}&team={team}")
    await page.evaluate(f"localStorage.setItem('beacon.welcome_seen.{person}', '1')")
    await page.goto(f"{BASE}{path}")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(1.2)


async def console_action(rec: Recorder, title: str) -> None:
    page = rec.page
    await page.keyboard.press("Shift+D")
    rec.mark("key", label="Shift + D")
    await asyncio.sleep(0.9)
    await rec.click(page.get_by_role("button", name=title).first, pause=0.6)


async def close_console(rec: Recorder) -> None:
    await rec.page.keyboard.press("Escape")
    await asyncio.sleep(0.6)


# --- Scene 0 and 1 -------------------------------------------------------------------------


async def prepare_signed_out(page: Page) -> None:
    await page.goto(f"{BASE}/")
    await page.evaluate(
        "sessionStorage.clear(); localStorage.removeItem('beacon.welcome_seen.anna')"
    )
    await page.goto(f"{BASE}/")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2.5)


async def s0_problem(rec: Recorder) -> None:
    rec.mark("zoom_slow", region={"x": 0, "y": 0, "w": 1440, "h": 810}, duration=14, factor=1.08)
    await rec.hold(12.5 / TEMPO)


async def s1_setup(rec: Recorder) -> None:
    page = rec.page
    await rec.hold(1.0)
    await rec.click(page.get_by_role("button", name="Anna Kowalska"), pause=1.6)
    rec.mark("caption", text="No password: pick who you are")
    await rec.hold(1.8)
    await rec.click(page.get_by_role("button", name="Next"), pause=0.5)
    await rec.zoom_on(page.locator("dialog[open] ol"), 3.2, factor=1.35)
    await rec.click(page.get_by_role("button", name="Next"), pause=0.8)
    await rec.hold(0.8)
    await rec.click(page.get_by_role("button", name="Send a test alert"), pause=0.2)
    await page.wait_for_url("**/inbox", timeout=15000)
    await page.get_by_text("Rejected EUR 25M").first.wait_for(timeout=15000)
    rec.mark("caption", text="About 1 s from event to alert")
    await rec.hold(1.0)
    await rec.click(page.get_by_text("Rejected EUR 25M").first, pause=1.0)
    await rec.hold(2.5)


SPEECH_STUB = """
(() => {
  window.__spoken = [];
  const synth = window.speechSynthesis;
  if (!synth) return;
  // Headless Chrome has no voices. Each line is spoken by macOS `say` on the recording machine
  // (window.__speakLine), and the page waits exactly that long, so the call in the film runs at
  // the real pace of the voice the editor dubs in.
  // Like the real API, utterances queue: each one starts when the one before has ended.
  let queue = Promise.resolve();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  synth.speak = (u) => {
    queue = queue.then(async () => {
      window.__spoken.push({ text: u.text, at: Date.now() });
      u.onstart && u.onstart(new Event('start'));
      const ms = window.__speakLine ? await window.__speakLine(u.text) : 900;
      await sleep(ms + 120);
      u.onend && u.onend(new Event('end'));
    });
  };
  synth.cancel = () => { queue = Promise.resolve(); };
})();
"""

PHONE_VOICE = "Samantha"
CURRENT: dict[str, Recorder] = {}


def phone_line_file(text: str) -> Path:
    digest = hashlib.sha1(f"{PHONE_VOICE}:{text}".encode()).hexdigest()[:12]
    return Path.home() / "Movies" / "beacon-demo" / "phone" / f"{digest}.aiff"


async def speak_line(text: str) -> int:
    """Speaks one call line into a file and logs where it starts in the clip."""
    path = phone_line_file(text)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            subprocess.run,
            ["say", "-v", PHONE_VOICE, "-r", "170", "-o", str(path), text],
            check=True,
        )
    probe = await asyncio.to_thread(
        subprocess.run,
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    seconds = float(probe.stdout)
    rec = CURRENT.get("rec")
    if rec is not None:
        rec.mark("phone_line", text=text, file=str(path), seconds=seconds)
    return int(seconds * 1000)


async def wait_until(rec: Recorder, clip_seconds: float) -> None:
    """Holds until the clip clock reaches `clip_seconds` (time the voiceover needs)."""
    while rec.now() < clip_seconds:
        await rec.hold(0.25 / TEMPO)


async def union_zoom(rec: Recorder, locators: list, seconds: float, factor: float = 1.5) -> None:
    boxes = [await rec.box(loc) for loc in locators]
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["w"] for b in boxes)
    y1 = max(b["y"] + b["h"] for b in boxes)
    seconds = max(MIN_ZOOM_SECONDS, seconds * TEMPO) / TEMPO
    rec.mark(
        "zoom",
        region={"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0},
        duration=seconds * TEMPO,
        factor=factor,
    )
    await rec.hold(seconds)


async def open_rail(rec: Recorder, label: str) -> None:
    # The rail label gains ", N pending" when something waits, so match the start only.
    link = rec.page.get_by_role("link", name=re.compile(rf"^{label}(,|$)"))
    await rec.click(link, pause=1.0)


async def replace_text(rec: Recorder, locator, text: str, delay_ms: int = 14) -> None:
    await rec.click(locator, pause=0.1)
    await locator.fill("")
    await locator.press_sequentially(text, delay=delay_ms)
    await asyncio.sleep(0.2)


# --- Scene 2: a team sets up alerting from nothing ------------------------------------------


async def s2a_connect(rec: Recorder) -> None:
    page = rec.page
    await rec.hold(1.0)
    await console_action(rec, "Event from a new system")
    await page.wait_for_url("**/connect", timeout=15000)
    map_button = page.get_by_role("button", name="Map this event").first
    await map_button.wait_for(timeout=20000)
    await rec.hold(0.8)
    rec.mark("caption", text="An event Beacon has never seen")
    await rec.zoom_on(page.locator("main li").first, 2.6, factor=1.4)
    await rec.click(map_button, pause=0.1)
    async with rec.cut(keep=0.9):
        await page.get_by_text("Beacon suggests this mapping").wait_for(timeout=120000)
        await asyncio.sleep(0.8)
    rec.mark("caption", text="The AI suggests a mapping. You check it.")
    await rec.hold(0.8)
    card = page.locator("main div.rounded-card").filter(has_text="Event type").first
    await rec.zoom_on(card, 4.0, factor=1.35)
    why = page.get_by_text("Why Beacon chose this")
    await why.scroll_into_view_if_needed()
    await rec.point(why)
    await rec.hold(2.0)
    await rec.click(page.get_by_role("button", name="Test this mapping"), pause=0.1)
    async with rec.cut(keep=0.7):
        await page.get_by_text("Matches your sample").wait_for(timeout=120000)
        await asyncio.sleep(0.6)
    await rec.hold(0.6)
    matches = (
        page.locator("main div")
        .filter(has_text="Matches your sample")
        .filter(has_text="Event type")
        .last
    )
    await rec.zoom_on(matches, 3.2, factor=1.4)
    await rec.click(page.get_by_role("button", name="Save mapping"), pause=0.6)
    await page.get_by_role("button", name="Create a rule for it").wait_for(timeout=20000)
    rec.mark("caption", text="Saved. No code, no restart.")
    await rec.hold(2.5)


async def s2b_runbook(rec: Recorder) -> None:
    page = rec.page
    await rec.hold(1.0)
    await rec.click(page.get_by_role("button", name="Add a runbook").first, pause=0.8)
    await replace_text(rec, page.get_by_label("Name", exact=True), "Payment declined check")
    box = page.get_by_label("Paste your runbook")
    await rec.click(box, pause=0.2)
    await box.fill(RUNBOOK_TEXT)
    rec.mark("caption", text="A runbook in plain words")
    await rec.zoom_on(box, 3.5, factor=1.35)
    await rec.click(page.get_by_role("button", name="Turn into steps"), pause=0.8)
    await rec.click(page.get_by_role("button", name="Save and read it"), pause=0.1)
    async with rec.cut(keep=0.9):
        await page.get_by_text("Beacon turned this into").wait_for(timeout=150000)
        await asyncio.sleep(0.8)
    await rec.hold(0.8)
    rec.mark("caption", text="4 steps. Risky ones wait for approval.")
    await union_zoom(
        rec,
        [page.get_by_text("Beacon turned this into"), page.get_by_text("Needs approval").last],
        4.5,
        factor=1.3,
    )
    await rec.hold(1.0)


async def s2c_rule(rec: Recorder) -> None:
    page = rec.page
    await rec.hold(1.0)
    await rec.click(page.get_by_role("button", name="New rule").first, pause=0.8)
    await replace_text(rec, page.get_by_label("Rule id"), "payments-declined")
    await replace_text(rec, page.get_by_label("Description"), "Declined payments")
    await replace_text(rec, page.get_by_label("Field").nth(0), "evt")
    await rec.select(page.get_by_label("Is it…").nth(0), "matches the pattern")
    await replace_text(
        rec, page.locator("input[placeholder='10000000']").nth(0), "payment.declined*"
    )
    await rec.click(page.get_by_role("button", name="Add condition"), pause=0.5)
    await replace_text(rec, page.get_by_label("Field").nth(1), "lvl")
    await rec.select(page.get_by_label("Is it…").nth(1), "at least severity")
    await page.get_by_text("Rule is valid").wait_for(timeout=15000)
    rec.mark("caption", text="When: a form, not code")
    await union_zoom(
        rec, [page.get_by_label("Field").nth(0), page.get_by_text("Rule is valid")], 2.4, factor=1.3
    )
    await rec.click(page.get_by_role("button", name="Next"), pause=0.8)
    title = page.get_by_label("Title", exact=True)
    await title.scroll_into_view_if_needed()
    await replace_text(rec, title, "Payment {{data.paymentId}} declined", delay_ms=12)
    await replace_text(
        rec,
        page.get_by_label("Text", exact=True),
        "{{data.amount}} {{data.currency}} declined: {{data.declineCode}}",
        delay_ms=10,
    )
    await rec.select(page.get_by_label("Runbook", exact=True), "Payment declined check")
    rec.mark("caption", text="Who, how, what it says, which runbook")
    await union_zoom(
        rec,
        [page.get_by_text("How the alert looks"), page.get_by_label("Runbook", exact=True)],
        2.6,
        factor=1.25,
    )
    await rec.click(page.get_by_role("button", name="Next"), pause=0.3)
    sentence = page.get_by_text("In the last hour this rule")
    await sentence.wait_for(timeout=60000)
    await rec.hold(0.6)
    rec.mark("caption", text="Preview: replayed on the last hour. Nothing sent.")
    await union_zoom(rec, [sentence, page.get_by_text("Who would be messaged")], 3.0, factor=1.3)
    advanced = page.get_by_text("edit as YAML")
    await advanced.scroll_into_view_if_needed()
    await rec.click(advanced, pause=1.0)
    rec.mark("caption", text="The same rule as YAML, ready for Git")
    await rec.scroll_by(260)
    await rec.hold(1.4)
    await rec.click(page.get_by_role("button", name="Save rule"), pause=1.2)
    rec.mark("caption", text="Saved. Every worker reloads live.")
    await rec.hold(1.2)


async def s2d_first_alert(rec: Recorder) -> None:
    page = rec.page
    await rec.hold(1.5)
    # The next event arrives from the payments system itself, so nothing is clicked: the alert
    # slides into the open Inbox live.
    await page.evaluate(
        """() => {
          const id = 'P-' + Math.random().toString(36).slice(2, 10).toUpperCase();
          return fetch('/api/v1/ingest/generic-webhook', {
            method: 'POST', headers: {'content-type': 'application/json'},
            body: JSON.stringify({evt: 'payment.declined', lvl: 'WARN', svc: 'payments-api',
              at: new Date().toISOString(),
              data: {paymentId: id, amount: 1250.0, currency: 'PLN',
                     declineCode: 'INSUFFICIENT_FUNDS'}})});
        }"""
    )
    rec.mark("caption", text="The next payment event arrives")
    row = page.get_by_text("declined", exact=False).filter(has_text="Payment P-").first
    await row.wait_for(timeout=20000)
    await rec.hold(1.6)
    await rec.click(row, pause=1.2)
    rec.mark("caption", text="Our title, our text, our runbook")
    heading = page.locator("main h2, main h1").filter(has_text="Payment P-").first
    await rec.zoom_on(heading, 2.8, 1.5)
    await rec.scroll_by(520, duration=1.6)
    await rec.hold(1.0)
    await rec.scroll_by(420, duration=1.4)
    waiting = page.get_by_text("Waiting for approval").first
    await waiting.scroll_into_view_if_needed()
    rec.mark("caption", text="The risky step waits for a human")
    await rec.zoom_on(waiting, 3.0, factor=1.5)


# --- Scene 3: a runbook that acts, and a phone that asks first ------------------------------


async def prepare_piotr(page: Page) -> None:
    await page.expose_function("__speakLine", speak_line)
    await page.add_init_script(SPEECH_STUB)
    await sign_in_as(page, "piotr", "settlements")


async def s3_phone(rec: Recorder) -> None:
    page = rec.page
    await rec.hold(1.0)
    await console_action(rec, "Settlement workflow fails")
    accept = page.get_by_role("button", name="Accept call")
    async with rec.cut(keep=1.2):
        await accept.wait_for(timeout=90000)
        await asyncio.sleep(0.3)
    rec.mark("caption", text="The runbook retried twice. Now it asks Piotr.")
    # Let it ring until the first part of the voiceover has been said.
    await wait_until(rec, 14.8)
    await rec.click(accept, pause=0.4)
    rec.mark("answered")
    # Zoom on the phone for the whole call: from the top of the screen to the end-call button.
    timer = await page.get_by_role("timer").bounding_box()
    end = await page.get_by_role("button", name="End call").bounding_box()
    call_started = rec.now()
    phone_region = None
    if timer and end:
        cx = end["x"] + end["width"] / 2
        top, bottom = timer["y"] - 70, end["y"] + end["height"] + 40
        phone_region = {"x": cx - 170, "y": top, "w": 340, "h": bottom - top}
    # Let the voice read the whole script, code included, before the keypad is used.
    await page.wait_for_function(
        "window.__spoken && window.__spoken.some(l => /press star/i.test(l.text))", timeout=90000
    )
    words = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
             "six": "6", "seven": "7", "eight": "8", "nine": "9"}  # fmt: skip
    spoken = [m for m in rec.marks if m["name"] == "phone_line"]
    code = "".join(words[m["text"].strip(". ")] for m in spoken if m["text"].strip(". ") in words)
    enter = next(m for m in spoken if "enter code" in m["text"].lower())
    # The caption appears as the phone starts reading the code, not after.
    rec.marks.append(
        {"name": "caption", "t": enter["t"], "text": f"Approval code {code}, read aloud"}
    )
    await wait_until(rec, spoken[-1]["t"] + spoken[-1]["seconds"] + 0.4)
    for digit in code:
        await rec.click(page.get_by_role("button", name=f"Key {digit}"), pause=0.45)
    rec.mark("keypad_done")
    await rec.hold(2.5)
    if phone_region is not None:
        rec.marks.append(
            {
                "name": "zoom",
                "t": round(call_started, 3),
                "region": phone_region,
                "duration": round(rec.now() - call_started, 3),
                "factor": 1.7,
            }
        )
    spoken = await page.evaluate("window.__spoken")
    rec.mark("speech", lines=spoken)
    await close_console(rec)
    await open_rail(rec, "Inbox")
    row = page.get_by_text("failed").filter(has_text="Workflow").first
    await row.wait_for(timeout=20000)
    await rec.click(row, pause=1.2)
    await rec.scroll_by(380, duration=1.4)
    rec.mark("caption", text="Every step recorded: what ran, who approved, how")
    await rec.hold(4.5)


# --- Scene 4: people and channels; propose a fix --------------------------------------------


async def s4_people_fix(rec: Recorder) -> None:
    page = rec.page
    await rec.hold(1.0)
    await rec.click(page.get_by_role("button", name="Edit").first, pause=1.0)
    rec.mark("caption", text="Each person picks channels and working hours")
    card = page.locator("main li.rounded-card").first
    await rec.point(page.get_by_text("Send by", exact=True))
    await rec.hold(0.8)
    await rec.point(page.get_by_text("Until", exact=True))
    await rec.zoom_on(card, 2.6, 1.15)
    await rec.click(page.get_by_role("button", name="Close").first, pause=0.6)
    await open_rail(rec, "Inbox")
    row = page.get_by_text("declined").filter(has_text="Payment P-").first
    await row.wait_for(timeout=20000)
    await rec.click(row, pause=1.0)
    await rec.click(page.get_by_role("button", name="Propose a fix"), pause=0.8)
    await rec.click(page.get_by_role("button", name="Draft with AI"), pause=0.1)
    async with rec.cut(keep=0.9):
        await page.wait_for_function(
            "!document.querySelector('dialog[open]')?.innerText.includes('Drafting')",
            timeout=150000,
        )
        await asyncio.sleep(0.8)
    rec.mark("caption", text="The AI drafts. It is only a proposal.")
    await rec.hold(2.0)
    await rec.click(page.get_by_role("button", name="Send proposal"), pause=1.0)
    await open_rail(rec, "Approvals")
    accept = page.get_by_role("button", name="Accept", exact=True).first
    await accept.wait_for(timeout=20000)
    await accept.scroll_into_view_if_needed()
    rec.mark("caption", text="The owning team sees the diff and accepts it")
    await rec.hold(1.6)
    await rec.click(accept, pause=0.2)
    await rec.hold(2.8)


# --- Scene 5: don't flood; never lose an alert ----------------------------------------------


async def s5a_dedup(rec: Recorder) -> None:
    page = rec.page
    await rec.hold(1.0)
    await console_action(rec, "500 identical events")
    async with rec.cut(keep=0.8):
        await page.get_by_text("Sent 500 duplicates").wait_for(timeout=60000)
    await close_console(rec)
    await open_rail(rec, "Inbox")
    badge = page.get_by_text("×500").first
    await badge.wait_for(timeout=20000)
    rec.mark("caption", text="500 events, 1 alert")
    await rec.zoom_on(badge, 3.0, factor=2.0)
    await rec.click(badge, pause=1.0)
    await rec.hold(2.0)


async def prepare_piotr_insights(page: Page) -> None:
    await page.expose_function("__speakLine", speak_line)
    await page.add_init_script(SPEECH_STUB)
    await sign_in_as(page, "piotr", "settlements", "/insights")


async def s5b_outage(rec: Recorder) -> None:
    page = rec.page
    channels = page.get_by_text("Channels", exact=True).first
    await channels.scroll_into_view_if_needed()
    await rec.hold(1.2)
    await console_action(rec, "Take SMS down")
    await asyncio.sleep(1.0)
    for _ in range(3):
        await rec.click(page.get_by_role("button", name="Settlement workflow fails"), pause=0.7)
    await close_console(rec)
    await channels.scroll_into_view_if_needed()
    async with rec.cut(keep=1.0):
        await page.get_by_text("Paused").first.wait_for(timeout=60000)
        await asyncio.sleep(0.5)
    rec.mark("caption", text="SMS down: paused, messages kept, others keep sending")
    await rec.zoom_on(
        page.locator("main section, main div.rounded-card").filter(has_text="Paused").last,
        4.0,
        1.35,
    )
    await console_action(rec, "Bring SMS back")
    await close_console(rec)
    sms_tile = page.locator("main li, main div.rounded-tile").filter(has_text="Text messages").last
    async with rec.cut(keep=1.0):
        await page.wait_for_function(
            """() => [...document.querySelectorAll('main li, main div')]
                 .some(e => e.innerText && e.innerText.startsWith('Text messages')
                            && e.innerText.includes('Nothing waiting'))""",
            timeout=120000,
        )
        await asyncio.sleep(1.0)
    rec.mark("caption", text="Back up. Queue drained. 0 lost.")
    await union_zoom(rec, [page.get_by_text("Email", exact=True).first, sms_tile], 3.2, factor=1.3)


# --- Scene 6: scale and numbers --------------------------------------------------------------


ROOT = Path(__file__).resolve().parents[2]


async def prepare_insights(page: Page) -> None:
    """Scale out and start a 70 s load run off-camera, so the charts move while we record."""
    await asyncio.to_thread(
        subprocess.run,
        ["docker", "compose", "up", "-d", "--scale", "processor=3", "--scale", "delivery=3"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    await asyncio.create_subprocess_exec(
        "uv", "run", "python", "loadtest/scenarios.py", "steady", "--duration", "70",
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    await asyncio.sleep(25)
    await sign_in_as(page, "anna", "rates", "/insights")


def scale_back() -> None:
    subprocess.run(
        ["docker", "compose", "up", "-d", "--scale", "processor=1", "--scale", "delivery=2"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


async def s6_scale(rec: Recorder) -> None:
    page = rec.page
    queues = page.get_by_text("Pipeline queues and deliveries")
    await queues.scroll_into_view_if_needed()
    await rec.scroll_by(200, duration=1.0)
    await rec.hold(1.2)
    rec.mark("caption", text="Under load: nothing dead-lettered, no backlog")
    tiles = page.locator("main div").filter(has_text="Dead-lettered").last
    await union_zoom(rec, [page.get_by_text("Retries", exact=True).first, tiles], 4.0, 1.3)
    await rec.glide(1420, 790, 0.4)
    await page.goto(
        "http://localhost:3000/d/alerting?orgId=1&viewPanel=8&from=now-5m&to=now&refresh=5s&kiosk"
    )
    await page.mouse.move(1435, 805)
    await asyncio.sleep(3.0)
    rec.mark("caption", text="3 processor replicas share the work. Scaling out is one command.")
    await rec.hold(7.0)
    scale_back()


# --- Scene 7: AI that helps, humans that decide ----------------------------------------------


async def s7_ai(rec: Recorder) -> None:
    page = rec.page
    await rec.hold(1.0)
    await rec.click(page.get_by_text("Payment declined check").first, pause=1.2)
    advanced = page.get_by_text("original text and version")
    await advanced.scroll_into_view_if_needed()
    await rec.click(advanced, pause=1.0)
    await rec.scroll_by(300)
    rec.mark("caption", text="Original words next to the steps. The AI only proposes.")
    await rec.hold(5.0)


def at(path: str, person: str = "anna", team: str = "rates") -> Callable[[Page], Awaitable[None]]:
    async def prepare(page: Page) -> None:
        await sign_in_as(page, person, team, path)

    return prepare


SCENES: dict[str, tuple[Callable[[Page], Awaitable[None]], Scene]] = {
    "s0-problem": (prepare_signed_out, s0_problem),
    "s1-setup": (prepare_signed_out, s1_setup),
    "s2a-connect": (at("/home"), s2a_connect),
    "s2b-runbook": (at("/runbooks"), s2b_runbook),
    "s2c-rule": (at("/rules"), s2c_rule),
    "s2d-first-alert": (at("/inbox"), s2d_first_alert),
    "s3-phone": (prepare_piotr, s3_phone),
    "s4-people-fix": (at("/people"), s4_people_fix),
    "s5a-dedup": (at("/home"), s5a_dedup),
    "s5b-outage": (prepare_piotr_insights, s5b_outage),
    "s6-scale": (prepare_insights, s6_scale),
    "s7-ai": (at("/runbooks"), s7_ai),
}


async def run_scene(
    context: BrowserContext, name: str, rec_factory: Callable[[Page], Recorder]
) -> None:
    prepare, scene = SCENES[name]
    page = await context.new_page()
    await prepare(page)
    rec = rec_factory(page)
    CURRENT["rec"] = rec
    await rec.start()
    try:
        await scene(rec)
    except Exception:
        await page.screenshot(path=str(rec.out_dir / "failure.png"))
        raise
    await rec.stop()
    await page.close()
