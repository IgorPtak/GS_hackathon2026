# ruff: noqa: E501  (inline CSS and SVG read better unwrapped)
"""Captions, chapter labels and title cards, drawn as HTML and saved as transparent 1080p PNGs."""

from __future__ import annotations

import asyncio
import hashlib
import html
from pathlib import Path

from playwright.async_api import async_playwright

FONT = "-apple-system, 'SF Pro Display', 'Helvetica Neue', system-ui, sans-serif"
MONO = "'SF Mono', ui-monospace, Menlo, monospace"

BASE_CSS = f"""
* {{ margin: 0; box-sizing: border-box; }}
html, body {{ width: 1920px; height: 1080px; background: transparent; font-family: {FONT};
  -webkit-font-smoothing: antialiased; }}
"""


def caption_html(text: str) -> str:
    return f"""<style>{BASE_CSS}
.c {{ position: absolute; left: 50%; bottom: 64px; transform: translateX(-50%);
  max-width: 1500px; padding: 18px 30px; border-radius: 22px; background: rgba(22,22,24,.86);
  color: #fff; font-size: 34px; font-weight: 600; letter-spacing: -.01em; line-height: 1.25;
  text-align: center; box-shadow: 0 18px 50px rgba(0,0,0,.28), 0 0 0 1px rgba(255,255,255,.08) inset; }}
</style><div class="c">{html.escape(text)}</div>"""


def chapter_html(text: str, number: int) -> str:
    return f"""<style>{BASE_CSS}
.k {{ position: absolute; right: 40px; bottom: 36px; padding: 9px 16px; border-radius: 999px;
  background: rgba(255,255,255,.78); color: #1d1d1f; font-size: 21px; font-weight: 600;
  box-shadow: 0 6px 20px rgba(0,0,0,.12), 0 0 0 1px rgba(0,0,0,.06) inset; }}
.k span {{ color: #86868b; margin-right: 8px; font-variant-numeric: tabular-nums; }}
</style><div class="k"><span>{number:02d}</span>{html.escape(text)}</div>"""


SETUP_CARD = f"""<style>{BASE_CSS}
body {{ background: radial-gradient(1200px 700px at 70% 30%, #ffffff 0%, #f2f2f5 60%, #e9e9ee 100%); }}
.wrap {{ position: absolute; left: 160px; top: 230px; }}
h1 {{ font-size: 76px; font-weight: 700; letter-spacing: -.03em; color: #1d1d1f; }}
p {{ margin-top: 18px; font-size: 34px; color: #6e6e73; }}
pre {{ margin-top: 54px; font-family: {MONO}; font-size: 32px; line-height: 1.75; color: #1d1d1f;
  background: #fff; border-radius: 28px; padding: 36px 48px; box-shadow: 0 30px 80px rgba(0,0,0,.10),
  0 0 0 1px rgba(0,0,0,.05); }}
pre b {{ color: #8e8e93; font-weight: 400; }}
.pill {{ display: inline-block; margin-top: 44px; font-size: 30px; font-weight: 600; color: #1a7f37;
  background: #e3f5e8; padding: 12px 24px; border-radius: 999px; }}
</style><div class="wrap"><h1>From a fresh clone</h1><p>Docker is the only thing you need.</p>
<pre><b>$</b> git clone https://github.com/IgorPtak/GS_hackathon2026.git
<b>$</b> cp .env.example .env
<b>$</b> docker compose up -d --build</pre>
<div class="pill">✓ Healthy in 18 s · first alert about 1 s after the event</div></div>"""

END_CARD = f"""<style>{BASE_CSS}
body {{ background: radial-gradient(1200px 700px at 50% 40%, #ffffff 0%, #f2f2f5 60%, #e7e7ec 100%); }}
.wrap {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center;
  justify-content: center; text-align: center; }}
.logo {{ width: 120px; height: 120px; border-radius: 32px; background: #1d1d1f; color: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 64px; }}
h1 {{ margin-top: 40px; font-size: 92px; font-weight: 700; letter-spacing: -.035em; color: #1d1d1f; }}
p {{ margin-top: 20px; font-size: 38px; color: #424245; max-width: 1300px; line-height: 1.3; }}
.url {{ margin-top: 56px; font-family: {MONO}; font-size: 30px; color: #0066cc; }}
</style><div class="wrap"><div class="logo">✦</div><h1>Beacon</h1>
<p>Teams change alerts without fear and without code,<br>and the AI only proposes.</p>
<div class="url">github.com/IgorPtak/GS_hackathon2026</div></div>"""


def overlay_path(out_dir: Path, kind: str, text: str) -> Path:
    digest = hashlib.sha1(f"{kind}:{text}".encode()).hexdigest()[:12]
    return out_dir / f"{kind}-{digest}.png"


async def render_pngs(items: list[tuple[str, Path, bool]]) -> None:
    """items: (html, path, is_transparent). Skips files that already exist."""
    todo = [item for item in items if not item[1].exists()]
    if not todo:
        return
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        for markup, path, is_transparent in todo:
            path.parent.mkdir(parents=True, exist_ok=True)
            await page.set_content(markup)
            await page.screenshot(path=str(path), omit_background=is_transparent)
        await browser.close()


def render(items: list[tuple[str, Path, bool]]) -> None:
    asyncio.run(render_pngs(items))


BENCH_ROWS = (
    ("Sustained, 3 replicas behind the proxy", "800 msg/s", "1.0 s", "0"),
    ("Steady, 60 s", "200 msg/s", "84 ms", "0"),
    ("Soak, 120 s", "250 msg/s", "461 ms", "0"),
    ("SMS gateway down for 60 s", "100 msg/s", "all 18,000 delivered", "0"),
    ("A processor killed mid-load", "200 msg/s", "all 24,000 delivered", "0"),
)

BENCH_CARD = f"""<style>{BASE_CSS}
body {{ background: radial-gradient(1200px 700px at 70% 30%, #ffffff 0%, #f2f2f5 60%, #e9e9ee 100%); }}
.wrap {{ position: absolute; left: 150px; right: 150px; top: 140px; }}
h1 {{ font-size: 70px; font-weight: 700; letter-spacing: -.03em; color: #1d1d1f; }}
p {{ margin-top: 14px; font-size: 30px; color: #6e6e73; }}
table {{ margin-top: 50px; width: 100%; border-collapse: separate; border-spacing: 0; background: #fff;
  border-radius: 28px; overflow: hidden; box-shadow: 0 30px 80px rgba(0,0,0,.10), 0 0 0 1px rgba(0,0,0,.05); }}
th, td {{ text-align: left; padding: 24px 34px; font-size: 31px; }}
th {{ font-size: 22px; text-transform: uppercase; letter-spacing: .06em; color: #86868b; font-weight: 600;
  border-bottom: 1px solid #ececf0; }}
td {{ border-bottom: 1px solid #f2f2f5; color: #1d1d1f; font-variant-numeric: tabular-nums; }}
tr:last-child td {{ border-bottom: 0; }}
td.n {{ font-weight: 600; }}
td.z {{ color: #1a7f37; font-weight: 700; }}
.foot {{ margin-top: 26px; font-size: 24px; color: #86868b; font-family: {MONO}; }}
</style><div class="wrap"><h1>Measured, not estimated</h1>
<p>End to end, from ingest to delivery. Apple M4 laptop, Docker Desktop.</p>
<table><tr><th>Scenario</th><th>Rate</th><th>p99</th><th>Lost</th></tr>
{"".join(f'<tr><td>{a}</td><td class="n">{b}</td><td class="n">{c}</td><td class="z">{d}</td></tr>' for a, b, c, d in BENCH_ROWS)}
</table><div class="foot">loadtest/scenarios.py · docs/load-test-results.md</div></div>"""
