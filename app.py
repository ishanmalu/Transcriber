#!/usr/bin/env python3
"""Local web UI for the transcriber. Run:  .venv/bin/python app.py"""
import json
import queue
import threading
import traceback
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

import core

HERE = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)

JOBS = {}          # id -> {"q": Queue, "segments": [...], "done": bool}
MAX_JOBS = 20      # transcripts are kept for download; drop the oldest beyond this
JOBS_LOCK = threading.Lock()
# Only one transcription at a time: the models are CPU-bound and memory-hungry.
RUN_LOCK = threading.Lock()


@app.get("/")
def index():
    return send_from_directory(HERE / "static", "index.html")


@app.get("/static/<path:name>")
def static_files(name):
    return send_from_directory(HERE / "static", name)


@app.post("/api/probe")
def api_probe():
    """Look up title/duration so the UI can show what's about to be transcribed."""
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="Paste a video link first."), 400
    try:
        return jsonify(core.probe(url, data.get("cookies_from_browser") or None))
    except core.TranscribeError as e:
        return jsonify(error=str(e)), 400


@app.post("/api/start")
def api_start():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="Paste a video link first."), 400
    try:
        start, end = core.resolve_range(
            data.get("range_mode", "whole"),
            start=data.get("start"), end=data.get("end"), duration=data.get("duration"))
    except core.TranscribeError as e:
        return jsonify(error=str(e)), 400

    model = core.MODELS.get(data.get("accuracy", "best"), "large-v3")
    job_id = uuid.uuid4().hex
    q = queue.Queue()
    with JOBS_LOCK:
        JOBS[job_id] = {"q": q, "segments": [], "done": False}
        for stale in [k for k, v in list(JOBS.items())[:-MAX_JOBS] if v["done"]]:
            JOBS.pop(stale, None)

    def emit(**payload):
        q.put(payload)

    def work():
        try:
            if RUN_LOCK.locked():
                emit(stage="status", message="Waiting for the current transcription to finish…")
            with RUN_LOCK:
                segments, _ = core.transcribe(
                    url, start=start, end=end, model=model,
                    lang=(data.get("lang") or None),
                    translate=bool(data.get("translate")),
                    cookies_from_browser=(data.get("cookies_from_browser") or None),
                    on_event=lambda **kw: emit(**kw))
            with JOBS_LOCK:
                JOBS[job_id]["segments"] = segments
            emit(stage="done", count=len(segments),
                 words=sum(len(s["text"].split()) for s in segments))
        except core.TranscribeError as e:
            emit(stage="error", message=str(e))
        except Exception:
            traceback.print_exc()
            emit(stage="error", message="Something went wrong. Check the terminal for details.")
        finally:
            with JOBS_LOCK:
                JOBS[job_id]["done"] = True
            q.put(None)

    threading.Thread(target=work, daemon=True).start()
    return jsonify(job_id=job_id)


@app.get("/api/stream/<job_id>")
def api_stream(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify(error="No such job."), 404

    def gen():
        while True:
            item = job["q"].get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/download/<job_id>.<fmt>")
def api_download(job_id, fmt):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or not job["segments"]:
        return jsonify(error="Nothing to download."), 404
    segs = job["segments"]
    if fmt == "srt":
        body, mime = core.to_srt(segs), "text/plain"
    elif fmt == "txt":
        body, mime = " ".join(s["text"] for s in segs), "text/plain"
    elif fmt == "stamped":
        body = "\n".join(f"[{core.fmt_ts(s['start'])}] {s['text']}" for s in segs)
        mime, fmt = "text/plain", "txt"
    else:
        return jsonify(error="Unknown format."), 400
    return Response(body, mimetype=mime, headers={
        "Content-Disposition": f'attachment; filename="transcript.{fmt}"'})


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--host", default="127.0.0.1",
                    help="0.0.0.0 exposes it to your local network (phone, iPad)")
    ap.add_argument("--no-browser", action="store_true",
                    help="don't open a browser tab (used when running at login)")
    opts = ap.parse_args()

    url = f"http://127.0.0.1:{opts.port}"
    print(f"\n  Transcriber running at {url}")
    if opts.host == "0.0.0.0":
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            print(f"  On your network:      http://{s.getsockname()[0]}:{opts.port}")
        except OSError:
            pass
        finally:
            s.close()
    print()
    if not opts.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=opts.host, port=opts.port, threaded=True, debug=False)
