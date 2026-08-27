#!/usr/bin/env python3
"""Shared transcription core used by both the CLI and the web UI."""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
YTDLP = str(HERE / ".venv" / "bin" / "yt-dlp")

MODELS = {
    "best": "large-v3",
    "balanced": "medium",
    "fast": "small",
}


class TranscribeError(Exception):
    """Anything the user can act on — shown directly in the UI."""


def parse_time(value):
    """Accept 90, 1:30, 00:01:30, 1m30s -> seconds (float)."""
    if value is None or value == "":
        return None
    v = str(value).strip()
    if re.fullmatch(r"\d+(\.\d+)?", v):
        return float(v)
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", v, re.I)
    if m and any(m.groups()):
        h, mi, s = (float(g or 0) for g in m.groups())
        return h * 3600 + mi * 60 + s
    parts = v.split(":")
    if all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts) and 2 <= len(parts) <= 3:
        secs = 0.0
        for p in parts:
            secs = secs * 60 + float(p)
        return secs
    raise TranscribeError(f"Can't read the time {value!r} — try 90, 1:30, or 1m30s.")


def fmt_ts(seconds, force_hours=False):
    seconds = max(0.0, float(seconds))
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if (h or force_hours) else f"{m:02d}:{s:02d}"


def srt_ts(seconds):
    seconds = max(0.0, float(seconds))
    ms = int(round((seconds - int(seconds)) * 1000))
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(segments):
    out = []
    for i, seg in enumerate(segments, 1):
        out.append(f"{i}\n{srt_ts(seg['start'])} --> {srt_ts(seg['end'])}\n{seg['text']}\n")
    return "\n".join(out)


def probe(url, cookies_from_browser=None):
    """Fetch title/duration/uploader without downloading. Returns {} on failure."""
    import json
    cmd = [YTDLP, "--no-playlist", "--skip-download", "--dump-single-json", url]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TranscribeError(_friendly_ytdlp_error(proc.stderr or proc.stdout))
    try:
        d = json.loads(proc.stdout)
    except ValueError:
        return {}
    return {
        "title": d.get("title"),
        "duration": d.get("duration"),
        "uploader": d.get("uploader") or d.get("channel"),
        "thumbnail": d.get("thumbnail"),
        "extractor": d.get("extractor_key"),
    }


def _friendly_ytdlp_error(raw):
    raw = (raw or "").strip()
    low = raw.lower()
    if "impersonat" in low:
        return ("TikTok/Instagram blocked the request because browser impersonation "
                "isn't available. Fix it with:\n\n"
                "  .venv/bin/pip install -U 'yt-dlp[default,curl-cffi]'")
    if "login" in low or "private" in low or "cookies" in low or "rate-limit" in low:
        return ("This video needs a login. Turn on “Use my browser login” in Advanced "
                "and pick the browser you're signed in to.")
    if "unsupported url" in low:
        return "That doesn't look like a video link I can open. Paste the full URL."
    if "unavailable" in low or "404" in low or "does not exist" in low:
        return "That video is unavailable — it may have been deleted or set to private."
    if "sign in to confirm" in low or "bot" in low:
        return ("The site is asking to confirm you're not a bot. Turn on “Use my browser "
                "login” in Advanced.")
    return "Couldn't download that video.\n\n" + raw[-800:]


def download_audio(url, workdir, cookies_from_browser=None):
    if not Path(YTDLP).exists():
        raise TranscribeError(f"yt-dlp is missing. Run: {HERE}/.venv/bin/pip install -U yt-dlp")
    out = workdir / "audio.%(ext)s"
    # Extract straight to 16 kHz mono — what Whisper wants anyway. Full-rate stereo
    # wav runs ~11 MB/min, which is gigabytes of temp space on a feature-length video.
    cmd = [YTDLP, "-f", "bestaudio/best", "-x", "--audio-format", "wav",
           "--postprocessor-args", "ExtractAudio:-ac 1 -ar 16000",
           "--no-playlist", "-o", str(out), url]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TranscribeError(_friendly_ytdlp_error(proc.stderr or proc.stdout))
    files = sorted(workdir.glob("audio.*"))
    if not files:
        raise TranscribeError("The download finished but produced no audio.")
    return files[0]


def clip(src, start, end, workdir):
    """Trim with ffmpeg, down to the 16 kHz mono wav Whisper wants."""
    if not shutil.which("ffmpeg"):
        raise TranscribeError("ffmpeg isn't installed. Run: brew install ffmpeg")
    dst = workdir / "clip.wav"
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(src)]
    if end:
        cmd += ["-to", str(end - (start or 0))]
    cmd += ["-ac", "1", "-ar", "16000", str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TranscribeError("Couldn't trim the audio:\n" + (proc.stderr or "")[-500:])
    if not dst.exists() or dst.stat().st_size < 1000:
        raise TranscribeError(
            "That time range is empty — it starts after the video ends. Check the range.")
    return dst


_MODEL_CACHE = {}


def load_model(name):
    """Models are big; keep one of each loaded per process."""
    from faster_whisper import WhisperModel
    if name not in _MODEL_CACHE:
        _MODEL_CACHE[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _MODEL_CACHE[name]


def resolve_range(mode, start=None, end=None, duration=None):
    """Turn the UI's three modes into (start_seconds, end_seconds)."""
    if mode == "whole":
        return None, None
    if mode == "first":
        d = parse_time(duration)
        if not d:
            raise TranscribeError("Tell me how much of the video to transcribe.")
        return None, d
    if mode == "range":
        s, e = parse_time(start), parse_time(end)
        if s is None and e is None:
            raise TranscribeError("Give a start time, an end time, or both.")
        if s is not None and e is not None and e <= s:
            raise TranscribeError("The end time has to come after the start time.")
        return s, e
    raise TranscribeError(f"Unknown range mode {mode!r}.")


def transcribe(url, *, start=None, end=None, model="large-v3", lang=None,
               translate=False, cookies_from_browser=None, on_event=lambda **k: None):
    """Run the full pipeline. on_event(stage=..., ...) reports progress."""
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)

        on_event(stage="download", message="Downloading audio…")
        audio = download_audio(url, workdir, cookies_from_browser)

        offset = start or 0.0
        if start or end:
            on_event(stage="trim", message="Trimming to your time range…")
            audio = clip(audio, start, end, workdir)

        on_event(stage="model", message=f"Loading the {model} model…")
        m = load_model(model)

        on_event(stage="transcribe", message="Transcribing…")
        segments, info = m.transcribe(
            str(audio),
            language=lang or None,
            task="translate" if translate else "transcribe",
            beam_size=5,
            vad_filter=True,                    # drop silence, avoids hallucinated text
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,   # stops repetition loops on short clips
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        )
        on_event(stage="language", language=info.language,
                 confidence=round(info.language_probability, 3),
                 audio_duration=round(info.duration, 1))

        collected = []
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            item = {"start": seg.start + offset, "end": seg.end + offset, "text": text}
            collected.append(item)
            on_event(stage="segment", **item)

        if not collected:
            raise TranscribeError(
                "No speech found in that audio — it may be music-only, or the time "
                "range may cover a silent part.")
        return collected, info
