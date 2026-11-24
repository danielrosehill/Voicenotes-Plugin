#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""Complete, verified export of a Voicenotes account: every note plus its original audio.

  full_export.py --out DIR [--dump voicenotes-indexeddb-dump.json] [--limit N] [--workers 6]
  full_export.py --out DIR --verify        # offline re-check of an existing export

Without a token (a logged-in browser page makes the API calls instead):
  full_export.py --out DIR --listing notes.json            # {recording_id: note} or [note, ...]
  full_export.py --out DIR --links-stdin < links.json      # [{"rid", "status", "url"}], repeat per batch
  full_export.py --out DIR --pending                       # ids still to fetch, as JSON

Token: VOICENOTES_TOKEN, or the first line of stdin with --token-stdin. It is never written to disk.

How it stays reliable
  * The API listing is the source of truth. A dump, if given, adds notes the listing misses.
    The listing is written only once every page was read.
  * One SQLite row per note (state.db), so a kill at any point resumes exactly.
  * A download is accepted only if it has the full Content-Length and looks like media (and, with
    ffprobe installed, decodes to a duration). It is written to .part, then renamed.
  * Signed links expire in about 5 minutes: a new one is fetched for each attempt.
  * 429/5xx/network errors back off and retry. A rejected token stops the run at once (exit 3):
    get a new one and run the same command. "No audio" needs a 404 from the API, never a guess.
  * Every run ends with a full verification and report.json.

Exit: 0 complete and verified, 1 some notes failed, 2 usage, 3 token rejected, 130 interrupted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

API = os.environ.get("VOICENOTES_API", "https://api.voicenotes.com/api")
SLEEP = float(os.environ.get("VOICENOTES_BACKOFF", "2"))
ATTEMPTS = 6
STOP, BAD_TOKEN = threading.Event(), threading.Event()
_pause_until = 0.0
_local = threading.local()
DB_LOCK = threading.Lock()


class Stopped(Exception):
    pass


class Permanent(Exception):
    """An answer that will not change by retrying."""


def wait(seconds: float) -> None:
    if STOP.wait(seconds):
        raise Stopped


def backoff(n: int) -> None:
    wait(min(120, SLEEP * 2**n) * random.uniform(0.7, 1.3))


def session() -> requests.Session:
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
    return _local.s


LINKS: dict[str, dict] = {}  # --links-stdin: rid -> {status, url}


def api(path: str, token: str) -> requests.Response:
    """GET with retries. Returns 200 or 404; anything else raises."""
    global _pause_until
    err = "?"
    for n in range(ATTEMPTS):
        if STOP.is_set():
            raise Stopped
        wait(max(0.0, _pause_until - time.monotonic()))  # a 429 pauses every worker
        try:
            r = session().get(API + path, timeout=60, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        except requests.RequestException as e:
            err = type(e).__name__
            backoff(n)
            continue
        if r.status_code == 200:
            try:
                r.json()
                return r
            except ValueError:
                err = "invalid JSON"
        elif r.status_code == 404:
            return r
        elif r.status_code in (401, 403):
            # One odd 403 on a single note is not a dead token; a 401 is.
            if r.status_code == 401:
                BAD_TOKEN.set()
                STOP.set()
                raise Stopped
            raise Permanent("HTTP 403")
        elif r.status_code == 429:
            ra = r.headers.get("Retry-After", "")
            _pause_until = time.monotonic() + (min(300, int(ra)) if ra.isdigit() else SLEEP * 2 ** (n + 1))
            err = "HTTP 429"
            continue
        else:
            err = f"HTTP {r.status_code}"
        backoff(n)
    raise RuntimeError(f"{path.split('?')[0]}: {err} after {ATTEMPTS} attempts")


def scrub(o):
    if isinstance(o, dict):
        return {k: scrub(v) for k, v in o.items() if k != "firebase_token"}
    return [scrub(x) for x in o] if isinstance(o, list) else o


def rid_of(r: dict) -> str:
    return str(r.get("recording_id") or r["id"])


def list_notes(token: str, limit: int) -> dict[str, dict]:
    """Every note. Notes added while paging shift pages, so overlaps are normal and deduplicated."""
    notes: dict[str, dict] = {}
    page, total_seen = 1, 0
    while True:
        r = api(f"/recordings?page={page}", token)
        if r.status_code != 200:
            raise RuntimeError(f"listing page {page}: HTTP {r.status_code}")
        body = r.json()
        data = body["data"]
        for x in data:
            notes.setdefault(rid_of(x), scrub(x))
        total_seen += len(data)
        if page % 25 == 0:
            print(f"listing: page {page}, {len(notes)} notes", flush=True)
        more = (body.get("links") or {}).get("next")
        if limit and len(notes) >= limit:
            return dict(list(notes.items())[:limit])
        if not more:
            return notes
        if not data:
            raise RuntimeError(f"listing page {page} is empty but has a next page")
        page += 1


def load_dump(p: Path) -> dict[str, dict]:
    out = {}
    for e in json.loads(p.read_text())["records"]:
        r = e["recording"] if isinstance(e.get("recording"), dict) else e
        out[rid_of(r)] = scrub(r)
    return out


def open_db(out: Path) -> sqlite3.Connection:
    db = sqlite3.connect(out / "state.db", check_same_thread=False, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS audio(rid TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending',
        file TEXT, bytes INTEGER, sha256 TEXT, seconds REAL, error TEXT, attempts INTEGER NOT NULL DEFAULT 0, updated TEXT)""")
    return db


def media_ok(head: bytes) -> bool:
    return (head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0) or head[4:8] == b"ftyp"
            or head[:4] in (b"RIFF", b"OggS", b"fLaC", b"\x1a\x45\xdf\xa3"))


def probe(p: Path) -> float | None:
    """Duration in seconds; None without ffprobe. Raises if ffprobe can't read the file."""
    if not shutil.which("ffprobe"):
        return None
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True, timeout=120)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise RuntimeError("ffprobe could not read the audio") from None


def fetch(rid: str, token: str, adir: Path) -> dict:
    err = "?"
    for n in range(ATTEMPTS):
        if STOP.is_set():
            raise Stopped
        if rid in LINKS:
            code, url = LINKS[rid].get("status"), LINKS[rid].get("url")
            if code not in (200, 404):
                return {"status": "failed", "error": f"link request: HTTP {code}"}
        else:
            r = api(f"/recordings/{rid}/signed-url", token)
            code = r.status_code
            url = r.json().get("url") if code == 200 else None
        if code == 404:
            return {"status": "no_audio", "error": "API 404"}
        if not url:
            return {"status": "no_audio", "error": "API returned no url"}
        ext = Path(urlparse(url).path).suffix.lower()
        dest = adir / f"{rid}{ext if 1 < len(ext) <= 6 and ext[1:].isalnum() else '.bin'}"
        part = dest.with_name(dest.name + ".part")
        try:
            h, size, head = hashlib.sha256(), 0, b""
            with session().get(url, stream=True, timeout=(30, 120), headers={"Accept-Encoding": "identity"}) as g:
                if g.status_code == 404:
                    return {"status": "missing", "error": "link given, file gone (storage 404)"}
                if g.status_code == 403 and rid in LINKS:
                    return {"status": "failed", "error": "link expired or refused (403)"}
                if g.status_code != 200:
                    raise RuntimeError(f"storage HTTP {g.status_code}")
                want = g.headers.get("Content-Length")
                with open(part, "wb") as f:
                    for c in g.iter_content(1 << 16):
                        if STOP.is_set():
                            raise Stopped
                        head = head or c[:16]
                        f.write(c)
                        h.update(c)
                        size += len(c)
                    f.flush()
                    os.fsync(f.fileno())
            if want is None or size != int(want):
                raise RuntimeError(f"short download: {size} of {want}")
            if size == 0:
                return {"status": "missing", "error": "zero-byte file in storage"}
            if not media_ok(head):
                raise RuntimeError("not a media file")
            secs = probe(part)
            part.replace(dest)
            return {"status": "ok", "file": dest.name, "bytes": size, "sha256": h.hexdigest(), "seconds": secs, "error": None}
        except Stopped:
            raise
        except (requests.RequestException, RuntimeError, OSError, subprocess.TimeoutExpired) as e:
            # Never log str(RequestException): it can contain the signed URL.
            err = type(e).__name__ if isinstance(e, requests.RequestException) else str(e)
            if isinstance(e, OSError) and not isinstance(e, requests.RequestException) and e.errno == 28:
                STOP.set()
                raise Stopped from None
        finally:
            part.unlink(missing_ok=True)
        backoff(n)
    raise RuntimeError(err)


def save_notes(out: Path, notes: dict[str, dict]) -> None:
    tmp = out / "notes.jsonl.tmp"
    with open(tmp, "w") as f:
        for r in sorted(notes.values(), key=lambda r: r.get("recorded_at") or r.get("created_at") or ""):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(out / "notes.jsonl")


def read_notes(out: Path) -> dict[str, dict]:
    p = out / "notes.jsonl"
    return {rid_of(r): r for r in map(json.loads, p.read_text().split("\n")[:-1])} if p.exists() else {}


def verify(out: Path, db: sqlite3.Connection) -> dict:
    """Re-hash every file against state.db and write manifest.jsonl and report.json."""
    notes = read_notes(out)
    state = {r[0]: r for r in db.execute("SELECT rid,status,file,bytes,sha256,seconds,error FROM audio")}
    counts: dict[str, int] = {}
    problems, total, known = [], 0, set()
    mismatch = []
    with open(out / "manifest.jsonl.tmp", "w") as mf:
        for rid, n in notes.items():
            _, status, file, size, sha, secs, err = state.get(rid, (rid, "pending", None, None, None, None, None))
            if status == "ok":
                p = out / "audio" / file
                known.add(file)
                h = hashlib.sha256()
                if p.exists():
                    with open(p, "rb") as f:
                        while b := f.read(1 << 20):
                            h.update(b)
                if h.hexdigest() != sha:
                    status, err = "pending", "file missing or changed on disk"
                    db.execute("UPDATE audio SET status='pending', error=? WHERE rid=?", (err, rid))
                else:
                    total += size
                    want = (n.get("duration") or 0) / 1000
                    if secs and want and abs(secs - want) > max(3, want * 0.1):
                        mismatch.append({"rid": rid, "api_seconds": want, "file_seconds": secs})
            counts[status] = counts.get(status, 0) + 1
            if status not in ("ok", "no_audio"):
                problems.append({"rid": rid, "recorded_at": n.get("recorded_at"), "status": status, "error": err})
            mf.write(json.dumps({"rid": rid, "recorded_at": n.get("recorded_at"), "title": n.get("title"), "audio_status": status,
                                 "audio_file": f"audio/{file}" if status == "ok" else None, "bytes": size, "sha256": sha,
                                 "seconds": secs, "has_transcript": bool((n.get("transcript") or "").strip())}, ensure_ascii=False) + "\n")
    (out / "manifest.jsonl.tmp").replace(out / "manifest.jsonl")
    rep = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "notes": len(notes),
           "with_transcript": sum(bool((n.get("transcript") or "").strip()) for n in notes.values()),
           "audio": counts, "audio_bytes": total, "complete": bool(notes) and not problems, "problems": problems,
           "duration_mismatches": mismatch,
           "stray_files": sorted(p.name for p in (out / "audio").glob("*") if p.name not in known)}
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--dump", type=Path)
    ap.add_argument("--limit", type=int, default=0, help="newest N notes only (trial run)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--token-stdin", action="store_true")
    ap.add_argument("--listing", type=Path)
    ap.add_argument("--links-stdin", action="store_true")
    ap.add_argument("--no-verify", action="store_true", help="with --links-stdin: skip the closing re-hash of everything")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--recheck-missing", action="store_true", help="ask again about notes recorded as having no audio")
    a = ap.parse_args()
    os.umask(0o077)
    (a.out / "audio").mkdir(parents=True, exist_ok=True)
    db = open_db(a.out)
    if a.pending:
        ok = {r[0] for r in db.execute("SELECT rid FROM audio WHERE status IN ('ok','no_audio')")}
        print(json.dumps([r for r in read_notes(a.out) if r not in ok]))
        return 0
    if a.links_stdin:
        LINKS.update({x["rid"]: x for x in json.load(sys.stdin)})
    token = ""
    if not a.verify and not a.listing and not a.links_stdin:
        token = (sys.stdin.readline() if a.token_stdin else os.environ.get("VOICENOTES_TOKEN", "")).strip()
        if not token:
            print("no token (VOICENOTES_TOKEN or --token-stdin)", file=sys.stderr)
            return 2
    if not a.verify:
        for s in (signal.SIGINT, signal.SIGTERM):
            signal.signal(s, lambda *_: STOP.set())
        for p in (a.out / "audio").glob("*.part"):
            p.unlink()
        try:
            if a.links_stdin:
                listed = {}
            elif a.listing:
                raw = json.loads(a.listing.read_text())
                listed = {rid_of(r): scrub(r) for r in (raw.values() if isinstance(raw, dict) else raw)}
            else:
                listed = list_notes(token, a.limit)
            notes = {**read_notes(a.out), **listed}  # never drop a note an earlier run saw
            if a.dump and not a.limit:
                extra = {k: v for k, v in load_dump(a.dump).items() if k not in notes}
                print(f"dump adds {len(extra)} notes the API listing did not return")
                notes |= extra
            save_notes(a.out, notes)
            db.executemany("INSERT OR IGNORE INTO audio(rid) VALUES (?)", [(k,) for k in notes])
            redo = "('ok')" if a.recheck_missing else "('ok','no_audio')"
            todo = [r[0] for r in db.execute(f"SELECT rid FROM audio WHERE status NOT IN {redo}") if r[0] in notes]
            if a.links_stdin:
                todo = [r for r in todo if r in LINKS]
            elif a.listing:
                todo = []
            print(f"{len(notes)} notes, {len(todo)} audio files to fetch", flush=True)
            done, t0 = 0, time.time()

            def one(rid: str) -> None:
                nonlocal done
                if STOP.is_set():
                    return
                try:
                    res = fetch(rid, token, a.out / "audio")
                except Stopped:
                    return
                except Exception as e:  # noqa: BLE001 - recorded, retried next run
                    res = {"status": "failed", "error": str(e)[:200]}
                with DB_LOCK:
                    db.execute("UPDATE audio SET status=?, file=?, bytes=?, sha256=?, seconds=?, error=?, attempts=attempts+1, updated=? WHERE rid=?",
                               (res["status"], res.get("file"), res.get("bytes"), res.get("sha256"), res.get("seconds"), res.get("error"),
                                datetime.now(timezone.utc).isoformat(timespec="seconds"), rid))
                    done += 1
                    if done % 100 == 0:
                        print(f"[{done}/{len(todo)}] {done / (time.time() - t0) * 60:.0f}/min", flush=True)

            with ThreadPoolExecutor(a.workers) as ex:
                list(ex.map(one, todo))
        except Stopped:
            pass
    if a.no_verify:
        print(json.dumps(dict(db.execute("SELECT status, COUNT(*) FROM audio GROUP BY 1").fetchall())))
        return 130 if STOP.is_set() else 0
    rep = verify(a.out, db)
    print(json.dumps({k: v if not isinstance(v, list) else len(v) for k, v in rep.items()}))
    if BAD_TOKEN.is_set():
        print("Token rejected. Get a fresh one and run the same command; finished files are kept.", file=sys.stderr)
        return 3
    if STOP.is_set():
        return 130
    return 0 if rep["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
