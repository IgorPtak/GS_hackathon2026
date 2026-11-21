# ruff: noqa: E501  (inline CSS and SVG read better unwrapped)
"""Scripted screen recording of the Beacon UI for the demo video.

Frames come from the Chrome DevTools screencast (sharp at 2x pixel density), so the clip is
identical on every take. A drawn cursor follows the mouse, because recordings never show the
real one. Waits on the AI or the network can be cut out while they happen (`with rec.cut():`),
and `mark()` logs moments the editor uses for captions and zooms.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import Locator, Page

VIEWPORT = {"width": 1440, "height": 810}
SCALE = 2
# Pauses and moves run at this share of their written length; the film has five minutes.
TEMPO = 0.65
MIN_ZOOM_SECONDS = 2.2

CURSOR_JS = """
(() => {
  if (window.__demoCursor) return;
  const c = document.createElement('div');
  c.id = '__demo_cursor';
  c.style.cssText = `position:fixed;left:0;top:0;width:22px;height:22px;z-index:2147483647;
    pointer-events:none;transform:translate(-3px,-2px);transition:opacity .2s;`;
  c.innerHTML = `<svg width="22" height="22" viewBox="0 0 22 22"><path d="M3 2 L3 18 L7.5 14 L10.5 20.5
    L13.2 19.3 L10.3 12.9 L16.5 12.9 Z" fill="#111" stroke="#fff" stroke-width="1.6"
    stroke-linejoin="round"/></svg>`;
  const ring = document.createElement('div');
  ring.style.cssText = `position:fixed;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;
    background:rgba(10,132,255,.28);pointer-events:none;z-index:2147483646;opacity:0;
    transform:scale(.4);transition:transform .35s cubic-bezier(.2,.8,.2,1),opacity .45s;`;
  const mount = () => {
    // Inside an open modal the top layer hides normal elements, so follow it there.
    const host = document.querySelector('dialog[open]') || document.body;
    if (c.parentNode !== host) { host.appendChild(ring); host.appendChild(c); }
  };
  document.addEventListener('mousemove', e => {
    mount(); c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px';
    ring.style.left = e.clientX + 'px'; ring.style.top = e.clientY + 'px';
  }, true);
  document.addEventListener('mousedown', () => {
    ring.style.transition = 'none'; ring.style.opacity = '1'; ring.style.transform = 'scale(.4)';
    requestAnimationFrame(() => { ring.style.transition = ''; ring.style.transform = 'scale(1.3)';
      ring.style.opacity = '0'; });
  }, true);
  new MutationObserver(mount).observe(document.documentElement, {subtree:true, childList:true,
    attributes:true, attributeFilter:['open']});
  window.__demoCursor = true;
})();
"""


@dataclass
class Recorder:
    """Collects screencast frames for one clip, with cuts and marks on the clip's own clock."""

    page: Page
    out_dir: Path
    frames: list[tuple[float, str]] = field(default_factory=list)
    marks: list[dict[str, Any]] = field(default_factory=list)
    _is_cutting: bool = False
    _cut_total: float = 0.0
    _cut_started: float | None = None
    _first: float | None = None
    _last_real: float = 0.0
    _mouse: tuple[float, float] = (720.0, 600.0)

    async def start(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for old in self.out_dir.glob("f*.jpg"):
            old.unlink()
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        await self.page.add_init_script(CURSOR_JS)
        await self.page.evaluate(CURSOR_JS)
        await self.cdp.send(
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": 92,
                "maxWidth": VIEWPORT["width"] * SCALE,
                "maxHeight": VIEWPORT["height"] * SCALE,
            },
        )
        await self.page.mouse.move(*self._mouse)

    def _on_frame(self, params: dict[str, Any]) -> None:
        asyncio.ensure_future(
            self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        )
        real = float(params["metadata"]["timestamp"])
        self._last_real = real
        if self._first is None:
            self._first = real
        if self._is_cutting:
            return
        clip_time = real - self._first - self._cut_total
        name = f"f{len(self.frames):06d}.jpg"
        (self.out_dir / name).write_bytes(base64.b64decode(params["data"]))
        self.frames.append((clip_time, name))

    def now(self) -> float:
        """Current time on the clip's clock (cuts removed)."""
        if self._first is None:
            return 0.0
        return max(0.0, time.time() - self._first - self._cut_total)

    async def hold(self, seconds: float) -> None:
        """Stillness the viewer sees. A tiny mouse wiggle keeps frames flowing."""
        seconds *= TEMPO
        steps = max(1, int(seconds / 0.25))
        for i in range(steps):
            x, y = self._mouse
            await self.page.mouse.move(x + (0.5 if i % 2 else -0.5), y)
            await asyncio.sleep(seconds / steps)

    @asynccontextmanager
    async def cut(self, keep: float = 0.6) -> AsyncIterator[None]:
        """Shows `keep` seconds of the wait, drops the rest from the clip."""
        await self.hold(keep)
        self._is_cutting = True
        started = time.time()
        try:
            yield
        finally:
            await asyncio.sleep(0.15)
            self._cut_total += max(0.0, time.time() - started)
            self._is_cutting = False

    def mark(self, name: str, **extra: Any) -> None:
        self.marks.append({"name": name, "t": round(self.now(), 3), **extra})

    async def box(self, locator: Locator, pad: int = 16) -> dict[str, float]:
        b = await locator.bounding_box()
        if b is None:
            return {"x": 0, "y": 0, "w": VIEWPORT["width"], "h": VIEWPORT["height"]}
        return {
            "x": max(0.0, b["x"] - pad),
            "y": max(0.0, b["y"] - pad),
            "w": b["width"] + 2 * pad,
            "h": b["height"] + 2 * pad,
        }

    async def zoom_on(self, locator: Locator, seconds: float, factor: float = 1.6) -> None:
        """Logs a zoom for the editor and holds still while it plays."""
        region = await self.box(locator)
        seconds = max(MIN_ZOOM_SECONDS, seconds * TEMPO) / TEMPO
        self.mark("zoom", region=region, duration=seconds * TEMPO, factor=factor)
        await self.hold(seconds)

    async def glide(self, x: float, y: float, duration: float = 0.55) -> None:
        """Moves the cursor along an eased path, like a hand would."""
        duration *= 0.75
        x0, y0 = self._mouse
        steps = max(8, int(duration * 60))
        for i in range(1, steps + 1):
            p = i / steps
            e = 0.5 - 0.5 * math.cos(math.pi * p)
            await self.page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
            await asyncio.sleep(duration / steps)
        self._mouse = (x, y)

    async def point(self, locator: Locator, duration: float = 0.55) -> None:
        await locator.scroll_into_view_if_needed()
        b = await locator.bounding_box()
        if b is None:
            return
        await self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, duration)

    async def click(self, locator: Locator, pause: float = 0.35) -> None:
        await self.point(locator)
        await asyncio.sleep(0.1)
        await self.page.mouse.down()
        await asyncio.sleep(0.07)
        await self.page.mouse.up()
        await asyncio.sleep(pause * TEMPO)

    async def type_into(self, locator: Locator, text: str, delay_ms: int = 14) -> None:
        await self.click(locator, pause=0.15)
        await locator.press_sequentially(text, delay=delay_ms)
        await asyncio.sleep(0.25)

    async def select(self, locator: Locator, label: str) -> None:
        await self.point(locator)
        await locator.select_option(label=label)
        await asyncio.sleep(0.4)

    async def scroll_by(self, dy: float, duration: float = 0.9) -> None:
        steps = max(6, int(duration * 40))
        for _ in range(steps):
            await self.page.mouse.wheel(0, dy / steps)
            await asyncio.sleep(duration / steps)

    async def stop(self) -> dict[str, Any]:
        await self.hold(0.6)
        await self.cdp.send("Page.stopScreencast")
        await asyncio.sleep(0.3)
        meta = {
            "frames": self.frames,
            "marks": self.marks,
            "duration": self.frames[-1][0] + 0.5 if self.frames else 0.0,
            "viewport": VIEWPORT,
        }
        (self.out_dir / "clip.json").write_text(json.dumps(meta, indent=1))
        return meta
