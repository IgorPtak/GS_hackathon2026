"""Turns a recorded clip (variable-rate JPEG frames + clip.json) into a 2880x1620 30 fps master.

The master stays at full capture size so zooms in the edit stay sharp at 1080p."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def frames_to_mp4(clip_dir: Path, out: Path, *, min_duration: float = 0.0) -> float:
    meta = json.loads((clip_dir / "clip.json").read_text())
    frames: list[tuple[float, str]] = meta["frames"]
    duration = max(meta["duration"], min_duration)
    lines = ["ffconcat version 1.0"]
    for i, (t, name) in enumerate(frames):
        end = frames[i + 1][0] if i + 1 < len(frames) else duration
        lines.append(f"file '{name}'")
        lines.append(f"duration {max(end - t, 0.001):.4f}")
    lines.append(f"file '{frames[-1][1]}'")
    (clip_dir / "frames.ffconcat").write_text("\n".join(lines) + "\n")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(clip_dir / "frames.ffconcat"),
            "-vf",
            "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "16",
            "-t",
            f"{duration:.3f}",
            str(out),
        ],
        check=True,
    )
    return duration
