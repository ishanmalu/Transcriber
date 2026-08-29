#!/usr/bin/env python3
"""Transcribe a TikTok / Instagram Reels / YouTube video from its URL.

Defaults to the WHOLE video; use --duration or --start/--end for a slice.
"""
import argparse
import sys
from pathlib import Path

import core


def main():
    p = argparse.ArgumentParser(
        description="Transcribe a TikTok / Reels / YouTube video. Whole video by default.")
    p.add_argument("url")
    p.add_argument("--start", help="start at (e.g. 0:30)")
    p.add_argument("--end", help="stop at (e.g. 2:15)")
    p.add_argument("--duration", help="how much to transcribe from --start (e.g. 60 or 1:00)")
    p.add_argument("--timestamps", dest="timestamps", action="store_true", default=True,
                   help="show [mm:ss] per line (default)")
    p.add_argument("--no-timestamps", dest="timestamps", action="store_false",
                   help="plain paragraph text, no timestamps")
    p.add_argument("--srt", action="store_true", help="output subtitle (.srt) format")
    p.add_argument("--model", default="large-v3",
                   help="tiny/base/small/medium/large-v3 (default: large-v3, most accurate)")
    p.add_argument("--lang", help="force language code (e.g. en, hi). Default: auto-detect")
    p.add_argument("--translate", action="store_true", help="translate to English")
    p.add_argument("--cookies-from-browser", help="e.g. chrome / safari — for login-gated videos")
    p.add_argument("-o", "--output", help="write to file instead of stdout")
    args = p.parse_args()

    try:
        if args.duration and args.end:
            p.error("use --duration or --end, not both")
        if args.duration:
            # --duration is relative to --start, so resolve both here; parse_time
            # raises on anything unreadable.
            start = core.parse_time(args.start)
            end = (start or 0) + core.parse_time(args.duration)
        elif args.start or args.end:
            start, end = core.resolve_range("range", start=args.start, end=args.end)
        else:
            start, end = None, None

        def on_event(stage=None, **kw):
            if stage in ("download", "trim", "model", "transcribe"):
                print(kw.get("message", stage), file=sys.stderr)
            elif stage == "language":
                print(f"Detected language: {kw['language']} ({kw['confidence']:.0%})",
                      file=sys.stderr)
            elif stage == "segment":
                print(".", end="", flush=True, file=sys.stderr)

        segments, _ = core.transcribe(
            args.url, start=start, end=end, model=args.model, lang=args.lang,
            translate=args.translate, cookies_from_browser=args.cookies_from_browser,
            on_event=on_event)
        print(file=sys.stderr)
    except core.TranscribeError as e:
        sys.exit(f"\n{e}")

    if args.srt:
        result = core.to_srt(segments)
    elif args.timestamps:
        result = "\n".join(f"[{core.fmt_ts(s['start'])}] {s['text']}" for s in segments)
    else:
        result = " ".join(s["text"] for s in segments)

    if args.output:
        Path(args.output).write_text(result + "\n")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
