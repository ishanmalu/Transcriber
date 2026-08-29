<p align="center">
  <img src="static/img/logo.svg" width="88" height="88" alt="">
</p>

<h1 align="center">Transcriber</h1>

<p align="center">
  Paste a TikTok, Instagram Reels, or YouTube link — get the transcript.<br>
  Runs entirely on your own machine. Nothing is uploaded anywhere.
</p>

<p align="center">
  <img alt="MIT" src="https://img.shields.io/badge/license-MIT-c25b34">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-c25b34">
</p>

---

## Install

Needs Python 3.10+ and [ffmpeg](https://ffmpeg.org) (`brew install ffmpeg`).

```bash
git clone https://github.com/ishanmalu/Transcriber.git
cd Transcriber
./setup.sh
```

## Run

Double-click **Transcriber.command**, or:

```bash
./Transcriber.command
```

It starts a local server and opens <http://127.0.0.1:5005> in your browser.

### From your phone or iPad

On the same Wi-Fi, start it with:

```bash
./.venv/bin/python app.py --host 0.0.0.0
```

It prints a `http://192.168.x.x:5005` address — open that on your phone.
Only devices on your network can reach it.

### From anywhere, with Tailscale

[Tailscale](https://tailscale.com) puts your own devices on a private network,
so your phone can reach this Mac from anywhere without exposing anything to the
public internet. With Tailscale installed and logged in on both devices:

```bash
./.venv/bin/python app.py --host "$(tailscale ip -4 | head -1)"
```

Then open `http://<your-machine>.<tailnet>.ts.net:5005` on any of your devices.
Traffic runs inside Tailscale's encrypted tunnel, and because the download still
happens from your home connection, TikTok and Instagram keep working — which is
not true of a cloud-hosted deployment.

### Always-on (optional)

To keep it running in the background so the address is always live — just a
bookmark, no launching anything:

```bash
./install-autostart.sh             # this Mac only
./install-autostart.sh tailscale   # reachable from your other devices
./install-autostart.sh 0.0.0.0     # reachable on your local network
```

Undo it any time with `./uninstall-autostart.sh`. Paste a link, pick how much of it
you want, hit Transcribe. Lines stream in as they're recognised; then Copy,
or download `.txt` / `.srt`.

**How much of it?**
- **Whole video** (default) — no length limit.
- **First…** — 30s / 1m / 5m / 10m presets, or type any length (`2:30`).
- **Time range** — from `0:30` to `2:15`. Leave either side blank for
  "from the start" / "to the end".

**Timestamps** toggle switches between `[0:04] line` and flowing paragraph text.
You can flip it after a run — it re-renders instantly, no re-transcribing.

**Accuracy**: Best (`large-v3`) / Balanced (`medium`) / Fast (`small`).

## Downloading the video or audio

Switch **What do you want?** to **Download file** and pick a format:

| | |
|---|---|
| **MP4** | video, merged from the best available streams |
| **MOV** | same video, remuxed for Final Cut and QuickTime |
| **MP3** | audio only, highest quality |

Video downloads take a **quality** cap: 480p, 720p, or 1080p (the maximum).
If the source was never published that large you get the biggest size it does
have, and the result card tells you what you actually got.

The time-range controls apply here too, so you can pull just a clip. Video trims
are stream-copied, so they're fast and land on the nearest keyframe.

Finished files land in `downloads/` and are cleaned up after 24 hours — save
anything you want to keep. Please respect the copyright of what you download.

**Advanced**: force a language, translate to English, or use your browser login
for private / login-gated posts.

## Command line

Whole video, with timestamps:

```bash
./.venv/bin/python transcribe.py "<url>"
```

| Flag | Does |
|---|---|
| `--duration 5:00` | only the first 5 minutes |
| `--start 0:30 --end 2:15` | a specific window |
| `--no-timestamps` | plain paragraph text |
| `--srt` | subtitle format |
| `--lang hi` / `--translate` | force language / translate to English |
| `--model small` | faster, less accurate |
| `-o out.txt` | write to a file |

## Why there's no hosted version

Transcriber runs on your machine on purpose, not just for privacy:

- **It needs a real server.** GitHub Pages and other static hosts can't run
  Python or a multi-gigabyte Whisper model, and a browser-only version can't
  fetch TikTok's media files (CORS).
- **Datacenter IPs get blocked.** TikTok, Instagram, and YouTube throttle or
  block cloud provider address ranges. Running from your own connection is the
  main reason downloads work reliably here.
- **Speed.** Transcription is CPU-bound. A cheap cloud instance is several times
  slower than an Apple silicon laptop.

## Privacy

Audio is downloaded to a temporary folder, transcribed by a local Whisper model,
and the folder is deleted when the run finishes. No audio, text, or links leave
your machine — there is no API key and no external service.

Times accept `90`, `1:30`, or `1m30s`.

## Accuracy notes

Uses Whisper `large-v3` by default with VAD silence-filtering and
`condition_on_previous_text=False` — those two matter a lot for TikTok/Reels,
where background music and short clips otherwise make Whisper hallucinate
repeated phrases.

First run of each model downloads it (~1.5 GB for `large-v3`), then it's cached.
Models are cached in `~/.cache/huggingface` after the first download.

## Speed and length limits

There is no maximum video length. Time is the only real constraint.
Measured on an M4 / 16 GB, transcription only (add download time):

| | Best (`large-v3`) | Fast (`small`) |
|---|---|---|
| speed | 1.8x realtime | 9.5x realtime |
| 1 min Reel/TikTok | ~35 sec | ~6 sec |
| 10 min | ~5.5 min | ~1 min |
| 30 min | ~17 min | ~3 min |
| 1 hour | ~33 min | ~6.5 min |
| 3 hours | ~1 hr 40 | ~19 min |

Disk: audio is extracted straight to 16 kHz mono, ~1.9 MB/min, so even a 3-hour
video is ~340 MB of temp space, deleted automatically when the run finishes.
RAM: `large-v3` holds ~1.6 GB while running.

One transcription runs at a time; a second request queues behind it.

## Upkeep

TikTok and Instagram change their internals often. If downloads start failing:

```bash
.venv/bin/pip install -U 'yt-dlp[default,curl-cffi]'
```

Always include the `[default,curl-cffi]` extra. TikTok rejects requests that don't
carry a real browser's TLS fingerprint, and `curl_cffi` is what supplies it —
without it you get an "attempting impersonation, but no impersonate target is
available" warning followed by a failed download.

## Layout

- `core.py` — download, trim, transcribe. Shared by both front ends.
- `transcribe.py` — CLI.
- `app.py` — Flask server (SSE streaming).
- `static/` — the web UI.

## License

MIT — see [LICENSE](LICENSE).
