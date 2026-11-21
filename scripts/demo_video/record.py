"""Records demo scenes into silent clips.

Usage (stack up, clean slate as in docs/demo.md):
  uv run --with playwright python scripts/demo_video/record.py s1-setup [s2a-connect ...]
  uv run --with playwright python scripts/demo_video/record.py --all
Clips land in ~/Movies/beacon-demo/raw/<scene>.mp4.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))

from frames import frames_to_mp4  # noqa: E402
from recorder import SCALE, VIEWPORT, Recorder  # noqa: E402
from scenes import SCENES, run_scene  # noqa: E402

OUT = Path.home() / "Movies" / "beacon-demo"


async def record(names: list[str], theme: str) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        for name in names:
            context = await browser.new_context(
                viewport=VIEWPORT, device_scale_factor=SCALE, color_scheme=theme
            )
            frames_dir = OUT / "frames" / name
            await run_scene(context, name, lambda page, d=frames_dir: Recorder(page, d))
            await context.close()
            (OUT / "raw").mkdir(parents=True, exist_ok=True)
            duration = frames_to_mp4(frames_dir, OUT / "raw" / f"{name}.mp4")
            print(f"{name}: {duration:.1f} s")
        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenes", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--theme", default="light", choices=["light", "dark"])
    args = parser.parse_args()
    names = list(SCENES) if args.all else args.scenes
    asyncio.run(record(names, args.theme))


if __name__ == "__main__":
    main()
