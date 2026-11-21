"""Edits the recorded clips into the demo film: zooms, captions, chapters, cards, voice.

Usage:
  uv run --with playwright python scripts/demo_video/render.py            # guide voice (say)
  uv run --with playwright python scripts/demo_video/render.py --voice ~/Movies/beacon-demo/voice
With --voice, a file named after a segment key (s1.wav, s3-1.m4a, ...) replaces that segment's
guide voice; keys without a file keep the guide voice. Output: ~/Movies/beacon-demo/beacon-demo.mp4
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cards import BENCH_CARD, END_CARD, SETUP_CARD, caption_html, chapter_html, overlay_path, render  # noqa: E402
from frames import frames_to_mp4  # noqa: E402
from narration import SEGMENTS, TIMELINE, Segment  # noqa: E402

OUT = Path.home() / "Movies" / "beacon-demo"
MASTER_W, MASTER_H = 2880, 1620
CSS_TO_MASTER = 2.0
RAMP = 0.7
CAPTION_SECONDS = 3.6
GUIDE_VOICE = "Daniel"
CARD_SECONDS = {"card-setup": 6.0, "card-bench": 7.0, "card-end": 6.5}
CARD_HTML = {"card-setup": SETUP_CARD, "card-bench": BENCH_CARD, "card-end": END_CARD}
TAIL = 0.9


def run(args: list[str]) -> None:
    subprocess.run(args, check=True)


def duration_of(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return float(out.strip())


# --- voice -------------------------------------------------------------------------------------


def voice_file(segment: Segment, voice_dir: Path | None) -> Path:
    if voice_dir is not None:
        for ext in (".wav", ".m4a", ".mp3", ".aiff", ".aif"):
            candidate = voice_dir / f"{segment.key}{ext}"
            if candidate.exists():
                return candidate
    guide = OUT / "guide" / f"{segment.key}.aiff"
    if (
        not guide.exists()
        or guide.stat().st_mtime < Path(__file__).with_name("narration.py").stat().st_mtime
    ):
        guide.parent.mkdir(parents=True, exist_ok=True)
        run(["say", "-v", GUIDE_VOICE, "-r", "178", "-o", str(guide), segment.text])
    return guide


def segment_start(segment: Segment, marks: list[dict]) -> float:
    if isinstance(segment.at, (int, float)):
        return float(segment.at)
    for mark in marks:
        if mark["name"] == segment.at:
            return mark["t"] + segment.after
    raise SystemExit(f"{segment.clip}: no mark '{segment.at}' (re-record that scene)")


def phone_lines(marks: list[dict]) -> list[tuple[float, Path]]:
    """The call script, dubbed with the same files the recording waited on, where they began."""
    return [(m["t"], Path(m["file"])) for m in marks if m["name"] == "phone_line"]


# --- picture -----------------------------------------------------------------------------------


def zoom_expressions(marks: list[dict]) -> tuple[str, str, str]:
    """zoompan z/x/y expressions: smooth push-ins on logged regions, then back out."""
    z_terms, x_terms, y_terms = [], [], []
    for mark in marks:
        if mark["name"] not in {"zoom", "zoom_slow"}:
            continue
        r = mark["region"]
        t0, d = mark["t"], mark["duration"]
        cx = (r["x"] + r["w"] / 2) * CSS_TO_MASTER
        cy = (r["y"] + r["h"] / 2) * CSS_TO_MASTER
        fit = min(MASTER_W / (r["w"] * CSS_TO_MASTER), MASTER_H / (r["h"] * CSS_TO_MASTER)) * 0.9
        z = max(1.0, min(mark["factor"], fit))
        if mark["name"] == "zoom_slow":
            s = f"between(it,{t0:.3f},{t0 + d:.3f})*((it-{t0:.3f})/{d:.3f})"
        else:
            p = f"max(0,min(1,min((it-{t0:.3f})/{RAMP},({t0 + d:.3f}-it)/{RAMP})))"
            s = f"between(it,{t0:.3f},{t0 + d:.3f})*({p})*({p})*(3-2*({p}))"
        z_terms.append(f"({s})*{z - 1:.4f}")
        x_terms.append(f"({s})*{cx - MASTER_W / 2:.1f}")
        y_terms.append(f"({s})*{cy - MASTER_H / 2:.1f}")
    zexpr = "1+" + "+".join(z_terms) if z_terms else "1"
    cx = f"{MASTER_W / 2}+" + "+".join(x_terms) if x_terms else f"{MASTER_W / 2}"
    cy = f"{MASTER_H / 2}+" + "+".join(y_terms) if y_terms else f"{MASTER_H / 2}"
    xexpr = f"max(0,min(iw-iw/zoom,({cx})-iw/zoom/2))"
    yexpr = f"max(0,min(ih-ih/zoom,({cy})-ih/zoom/2))"
    return zexpr, xexpr, yexpr


def captions_of(marks: list[dict]) -> list[tuple[float, float, str]]:
    caps = [(m["t"], m["text"]) for m in marks if m["name"] == "caption"]
    out = []
    for i, (t, text) in enumerate(caps):
        end = t + CAPTION_SECONDS
        if i + 1 < len(caps):
            end = min(end, caps[i + 1][0] - 0.15)
        out.append((t, end, text))
    return out


def build_clip(name: str, chapter: str, number: int, target: float) -> Path:
    clip_dir = OUT / "frames" / name
    master = OUT / "raw" / f"{name}.mp4"
    if not master.exists() or duration_of(master) < 1:
        frames_to_mp4(clip_dir, master)
    meta = json.loads((clip_dir / "clip.json").read_text())
    marks = meta["marks"]
    zexpr, xexpr, yexpr = zoom_expressions(marks)
    overlays: list[tuple[Path, float, float]] = []
    pngs: list[tuple[str, Path, bool]] = []
    for start, end, text in captions_of(marks):
        path = overlay_path(OUT / "overlays", "caption", text)
        pngs.append((caption_html(text), path, True))
        overlays.append((path, start, end))
    if chapter:
        path = overlay_path(OUT / "overlays", "chapter", f"{number}:{chapter}")
        pngs.append((chapter_html(chapter, number), path, True))
        overlays.append((path, 0.0, target))
    render(pngs)

    inputs = ["-i", str(master)]
    for path, _, _ in overlays:
        inputs += ["-loop", "1", "-framerate", "30", "-t", f"{target:.3f}", "-i", str(path)]
    filters = [
        f"[0:v]tpad=stop_mode=clone:stop_duration={max(0.0, target - meta['duration']) + 1:.3f},"
        f"zoompan=z='{zexpr}':x='{xexpr}':y='{yexpr}':d=1:fps=30:s=1920x1080,"
        "setsar=1,format=yuv420p[v0]"
    ]
    last = "v0"
    for i, (_, start, end) in enumerate(overlays, start=1):
        fade = (
            f"fade=t=in:st={start:.3f}:d=0.3:alpha=1,"
            f"fade=t=out:st={max(start, end - 0.3):.3f}:d=0.3:alpha=1"
            if end < target - 0.01
            else f"fade=t=in:st={start:.3f}:d=0.3:alpha=1"
        )
        filters.append(f"[{i}:v]format=rgba,{fade}[o{i}]")
        filters.append(f"[{last}][o{i}]overlay=0:0:format=auto[v{i}]")
        last = f"v{i}"
    out = OUT / "edit" / f"{name}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{last}]",
            "-t",
            f"{target:.3f}",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "17",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ]
    )
    return out


def build_card(name: str, seconds: float) -> Path:
    png = OUT / "overlays" / f"{name}.png"
    render([(CARD_HTML[name], png, False)])
    out = OUT / "edit" / f"{name}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    fade_out = f",fade=t=out:st={seconds - 0.5:.2f}:d=0.5" if name == "card-end" else ""
    run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-t",
            f"{seconds}",
            "-i",
            str(png),
            "-vf",
            f"zoompan=z='1+0.03*on/({seconds}*30)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:fps=30:"
            f"s=1920x1080,fade=t=in:st=0:d=0.4{fade_out},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "17",
            "-r",
            "30",
            str(out),
        ]
    )
    return out


# --- film --------------------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", type=Path, default=None, help="folder with recorded segments")
    parser.add_argument("--out", type=Path, default=OUT / "beacon-demo.mp4")
    args = parser.parse_args()

    audio_parts: list[tuple[float, Path, float]] = []  # (absolute start, file, gain)
    pieces: list[Path] = []
    clock = 0.0
    number = 0
    seen_chapters: list[str] = []
    for name, chapter in TIMELINE:
        if chapter and chapter not in seen_chapters:
            seen_chapters.append(chapter)
        number = seen_chapters.index(chapter) + 1 if chapter else number
        if name.startswith("card-"):
            seconds = CARD_SECONDS[name]
            for segment in (s for s in SEGMENTS if s.clip == name):
                voice = voice_file(segment, args.voice)
                start = float(segment.at) if isinstance(segment.at, (int, float)) else 0.5
                audio_parts.append((clock + start, voice, 1.0))
                seconds = max(seconds, start + duration_of(voice) + TAIL)
            pieces.append(build_card(name, seconds))
            print(f"{name:18s} {seconds:6.1f} s  (at {clock:6.1f} s)")
            clock += seconds
            continue
        meta = json.loads((OUT / "frames" / name / "clip.json").read_text())
        marks = meta["marks"]
        end = meta["duration"]
        for segment in (s for s in SEGMENTS if s.clip == name):
            voice = voice_file(segment, args.voice)
            start = segment_start(segment, marks)
            audio_parts.append((clock + start, voice, 1.0))
            end = max(end, start + duration_of(voice) + TAIL)
        if name == "s3-phone":
            for start, path in phone_lines(marks):
                audio_parts.append((clock + start, path, 0.85))
        pieces.append(build_clip(name, chapter, number, end))
        print(f"{name:18s} {end:6.1f} s  (at {clock:6.1f} s)")
        clock += end

    concat = OUT / "edit" / "concat.txt"
    concat.write_text("".join(f"file '{p}'\n" for p in pieces))
    silent = OUT / "edit" / "film-silent.mp4"
    run(
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
            str(concat),
            "-c",
            "copy",
            str(silent),
        ]
    )

    inputs: list[str] = []
    mixes: list[str] = []
    for i, (start, path, gain) in enumerate(audio_parts):
        inputs += ["-i", str(path)]
        ms = int(start * 1000)
        # Recorded voices: cut rumble and hiss, even out peaks, and bring every segment to the
        # same loudness, so two speakers and quiet takes match. Synth voices are already clean.
        is_recorded = OUT / "guide" not in path.parents and OUT / "phone" not in path.parents
        voice_chain = (
            "highpass=f=80,afftdn=nf=-30,"
            "acompressor=threshold=-24dB:ratio=3:attack=10:release=200,"
            "loudnorm=I=-18:TP=-2:LRA=7,aresample=48000,"
            if is_recorded
            else ""
        )
        mixes.append(
            f"[{i + 1}:a]silenceremove=start_periods=1:start_threshold=-45dB,{voice_chain}"
            f"aformat=sample_rates=48000:channel_layouts=stereo,volume={gain},"
            f"adelay={ms}|{ms}[a{i}]"
        )
    labels = "".join(f"[a{i}]" for i in range(len(audio_parts)))
    mixes.append(
        f"{labels}amix=inputs={len(audio_parts)}:normalize=0,loudnorm=I=-16:TP=-1.5,aresample=48000,apad[aout]"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(silent),
            *inputs,
            "-filter_complex",
            ";".join(mixes),
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(args.out),
        ]
    )
    print(f"\n{args.out}  {duration_of(args.out):.1f} s")


if __name__ == "__main__":
    main()
