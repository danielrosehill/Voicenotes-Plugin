#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""Voicenotes account exporter — end-to-end, parallel, resumable.

Lists recordings (via paginated API or a pre-saved IndexedDB dump), writes
one Markdown note per recording, downloads original audio via the per-recording
signed-url endpoint, and maintains catalog.json + state.json. Audio downloads
run in a thread pool — empirically ~150 rec/min with 8 workers, ~10× the serial
rate, and the API doesn't rate-limit at that level.

Usage:
    export VOICENOTES_TOKEN='<JSON.parse(localStorage.auth_token)>'

    # Full pull, list via API:
    python voicenotes_export.py --out ./voicenotes-export

    # Skip API listing, use IndexedDB dump for metadata (faster + offline-safe):
    python voicenotes_export.py --out ./voicenotes-export \\
        --from-dump ./voicenotes-export/voicenotes-indexeddb-dump.json

    # Tuning:
    python voicenotes_export.py --out ./voicenotes-export --workers 8
    python voicenotes_export.py --out ./voicenotes-export --no-audio
    python voicenotes_export.py --out ./voicenotes-export --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

API_BASE = "https://api.voicenotes.com/api"
PAGE_DELAY = 0.4
MAX_RETRIES = 5

STATE_LOCK = threading.Lock()
STOP = threading.Event()


def slugify(text: str, maxlen: int = 60) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:maxlen] or "untitled"


def yaml_escape(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def build_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "voicenotes-plugin-export/0.2 (+personal backup)",
    })
    return s


def request_with_retry(session: requests.Session, method: str, url: str, **kw) -> requests.Response:
    last_resp = None
    for attempt in range(MAX_RETRIES):
        if STOP.is_set():
            raise SystemExit(130)
        try:
            resp = session.request(method, url, timeout=60, **kw)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        last_resp = resp
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 2 ** attempt))
            print(f"  rate-limited, sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if 500 <= resp.status_code < 600:
            time.sleep(2 ** attempt)
            continue
        return resp
    if last_resp is not None:
        last_resp.raise_for_status()
    raise RuntimeError(f"failed: {url}")


def list_recordings_api(session: requests.Session) -> list[dict]:
    items: list[dict] = []
    url = f"{API_BASE}/recordings"
    page = 1
    while url:
        print(f"Fetching page {page}...")
        resp = request_with_retry(session, "GET", url)
        body = resp.json()
        items.extend(body.get("data", []))
        url = (body.get("links") or {}).get("next")
        page += 1
        if url:
            time.sleep(PAGE_DELAY)
    return items


def list_recordings_dump(dump_path: Path) -> list[dict]:
    """Read the IndexedDB dump (scripts/dump_indexeddb.js output).

    Cache has two shapes: one wrapper record with {recording: {...}} and the
    rest flat with the recording fields at top level.
    """
    raw = json.loads(dump_path.read_text())
    items = raw.get("records") or raw.get("recordings") or raw if isinstance(raw, dict) else raw
    out = []
    for it in items:
        if isinstance(it, dict) and "recording" in it and isinstance(it["recording"], dict):
            out.append(it["recording"])
        elif isinstance(it, dict) and ("recording_id" in it or "id" in it):
            out.append(it)
    return out


def get_signed_url(session: requests.Session, rid: str) -> str | None:
    try:
        resp = request_with_retry(session, "GET", f"{API_BASE}/recordings/{rid}/signed-url")
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    return resp.json().get("url")


def audio_extension(url: str, default: str = "mp3") -> str:
    return (Path(urlparse(url).path).suffix.lstrip(".").lower()) or default


def download_audio(url: str, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        size = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if STOP.is_set():
                    f.close()
                    tmp.unlink(missing_ok=True)
                    return 0
                if chunk:
                    f.write(chunk)
                    size += len(chunk)
    tmp.rename(dest)
    return size


def render_markdown(rec: dict) -> str:
    fm: list[str] = ["---"]
    keys = [
        "id", "recording_id", "parent_id", "title", "recorded_at", "created_at",
        "updated_at", "duration", "public_slug", "is_published",
        "recording_type", "user_id", "user_name",
    ]
    for k in keys:
        if k in rec:
            fm.append(f"{k}: {yaml_escape(rec.get(k))}")
    tags = rec.get("tags") or []
    if tags:
        fm.append("tags:")
        for t in tags:
            name = t.get("name") if isinstance(t, dict) else t
            fm.append(f"  - {yaml_escape(name)}")
    creations = rec.get("creations") or []
    if creations:
        fm.append("creations:")
        for c in creations:
            ctype = c.get("type") or c.get("creation_type") or "creation"
            cid = c.get("id") or c.get("creation_id") or ""
            fm.append(f"  - {yaml_escape(f'{ctype}:{cid}')}")
    if rec.get("attachments"):
        fm.append(f"attachments_count: {len(rec['attachments'])}")
    fm.append("---")
    fm.append("")

    body = [f"# {rec.get('title') or 'Untitled'}", ""]
    body.append((rec.get("transcript") or "").strip() or "_(no transcript)_")
    body.append("")
    for c in creations:
        ctype = c.get("type") or c.get("creation_type") or "creation"
        content = c.get("content") or c.get("markdown_content") or c.get("text") or ""
        if content:
            body += ["", f"## Creation: {ctype}", "", str(content).strip(), ""]
    return "\n".join(fm + body)


def note_filename(rec: dict) -> str:
    rid = rec.get("recording_id") or rec.get("id") or "unknown"
    recorded = (rec.get("recorded_at") or rec.get("created_at") or "")[:10]
    slug = slugify(rec.get("title") or "")
    return f"{recorded}__{rid}__{slug}.md"


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)


def fetch_audio(token: str, rid: str, audio_dir: Path) -> tuple[str, bool, int, str]:
    if STOP.is_set():
        return rid, False, 0, "stopped"
    existing = [p for p in audio_dir.glob(f"{rid}.*") if not p.name.endswith(".part")]
    if existing:
        return rid, True, existing[0].stat().st_size, "already-on-disk"
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
    url = get_signed_url(s, rid)
    if not url:
        return rid, False, 0, "no-signed-url"
    try:
        size = download_audio(url, audio_dir / f"{rid}.{audio_extension(url)}")
    except Exception as e:
        return rid, False, 0, f"download-failed: {e}"
    if size == 0:
        return rid, False, 0, "stopped-mid-download"
    return rid, True, size, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--from-dump", type=Path,
                    help="Use IndexedDB dump for metadata instead of API listing")
    ap.add_argument("--workers", type=int, default=8,
                    help="Parallel audio downloaders (default 8)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    token = os.environ.get("VOICENOTES_TOKEN", "").strip()
    if not token:
        print("ERROR: set VOICENOTES_TOKEN env var (JSON.parse(localStorage.auth_token))",
              file=sys.stderr)
        return 2

    out: Path = args.out
    notes_dir = out / "notes"
    audio_dir = out / "audio"
    state_path = out / "state.json"
    catalog_path = out / "catalog.json"
    if not args.dry_run:
        notes_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)

    session = build_session(token)
    if args.from_dump:
        print(f"Reading recordings from dump: {args.from_dump}")
        recordings = list_recordings_dump(args.from_dump)
    else:
        recordings = list_recordings_api(session)
    print(f"Found {len(recordings)} recordings.")
    if args.limit:
        recordings = recordings[: args.limit]

    if args.dry_run:
        total_dur = sum(int(r.get("duration") or 0) for r in recordings)
        print(f"Total duration: {total_dur}s ({total_dur/3600:.1f}h)")
        for r in recordings[:10]:
            print(f"  - [{r.get('recording_id')}] {r.get('title')!r}  {r.get('duration')}s")
        return 0

    state = json.loads(state_path.read_text()) if state_path.exists() else {"notes_done": [], "audio_done": []}
    notes_done = set(state.get("notes_done", []))
    audio_done = set(state.get("audio_done", []))

    catalog: list[dict] = []
    pending_audio: list[str] = []

    print("Writing notes + building catalog...")
    for rec in recordings:
        rid = rec.get("recording_id") or str(rec.get("id"))
        md_path = notes_dir / note_filename(rec)
        if rid not in notes_done or not md_path.exists():
            md_path.write_text(render_markdown(rec))
            notes_done.add(rid)
        catalog.append({
            "recording_id": rid,
            "id": rec.get("id"),
            "title": rec.get("title"),
            "recorded_at": rec.get("recorded_at"),
            "duration": rec.get("duration"),
            "tags": [t.get("name") if isinstance(t, dict) else t for t in (rec.get("tags") or [])],
            "note_file": str(md_path.relative_to(out)),
        })
        if not args.no_audio and rid not in audio_done:
            pending_audio.append(rid)

    state["notes_done"] = sorted(notes_done)
    save_state(state_path, state)
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
    print(f"Notes: {len(notes_done)}  Catalog: {catalog_path}")

    if args.no_audio or not pending_audio:
        print("Done (no audio).")
        return 0

    def handle_sigint(signum, frame):
        if STOP.is_set():
            sys.exit(130)
        print("\nstopping after current downloads — Ctrl-C again to force")
        STOP.set()
    signal.signal(signal.SIGINT, handle_sigint)

    print(f"Downloading audio: {len(pending_audio)} pending, {args.workers} workers")
    t0 = time.time()
    ok = 0
    failed: list[tuple[str, str]] = []
    total_bytes = 0
    done_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch_audio, token, rid, audio_dir): rid for rid in pending_audio}
        for fut in as_completed(futures):
            rid, success, size, reason = fut.result()
            done_count += 1
            if success:
                ok += 1
                total_bytes += size
                with STATE_LOCK:
                    audio_done.add(rid)
                    state["audio_done"] = sorted(audio_done)
                    save_state(state_path, state)
                if done_count % 25 == 0 or done_count == len(pending_audio):
                    rate = done_count / (time.time() - t0) * 60
                    print(f"[{done_count}/{len(pending_audio)}] ok={ok} fail={len(failed)} "
                          f"{total_bytes/1e6:.0f} MB  rate={rate:.0f}/min")
            else:
                failed.append((rid, reason))
                print(f"  FAIL {rid}: {reason}")

    elapsed = time.time() - t0
    print("---")
    print(f"audio: {ok}/{len(pending_audio)} ok, {len(failed)} fail in {elapsed/60:.1f} min")
    print(f"bytes: {total_bytes/1e6:.0f} MB")
    if failed:
        (out / "failed.json").write_text(json.dumps(failed, indent=2))
        print(f"failures logged to {out / 'failed.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
