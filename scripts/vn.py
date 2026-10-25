#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""Unofficial Voicenotes private-API helper: tags and audio import.

Uses the endpoints the voicenotes.com web app itself calls (read from its
bundle and verified live on 2026-10-25). Undocumented; can break without notice.

Auth: the web app's Bearer token. In DevTools on https://voicenotes.com/app:
    copy(JSON.parse(localStorage.auth_token))
then `export VOICENOTES_TOKEN='<paste>'`. The JSON.parse matters: the raw
localStorage value is quote-wrapped and gets 401.

Usage:
    vn.py tags                                 # all tags: id, name, note count
    vn.py show <note_id>                       # title, date, current tags
    vn.py set-tags <note_id> Tag1 Tag2         # replace the note's tags
    vn.py add-tags <note_id> Tag1 [Tag2 ...]
    vn.py remove-tags <note_id> Tag1 [Tag2 ...]
    vn.py import-audio <file> [--wait]         # import an audio file as a note

Tags are passed by name. Output is JSON.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import random
import shutil
import string
import subprocess
import sys
import time
from pathlib import Path

import requests

API_BASE = "https://api.voicenotes.com/api"
IMPORT_TYPE_AUDIO = 3  # web app: .md -> 1, application/pdf -> 2, audio/* -> 3, other -> 4
MAX_AUDIO_MB = 100     # web app limit for audio imports (other file types: 50)


def session() -> requests.Session:
    token = os.environ.get("VOICENOTES_TOKEN", "").strip().strip('"')
    if not token:
        sys.exit("set VOICENOTES_TOKEN (DevTools: copy(JSON.parse(localStorage.auth_token)))")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
    return s


def call(s: requests.Session, method: str, path: str, **kw) -> dict:
    r = s.request(method, f"{API_BASE}{path}", timeout=60, **kw)
    if r.status_code == 401:
        sys.exit("401 Unauthenticated: token missing, quote-wrapped or expired")
    r.raise_for_status()
    return r.json() if r.content else {}


def unwrap(body: dict) -> dict:
    return body.get("data", body) if isinstance(body, dict) else body


def get_note(s, note_id: str) -> dict:
    return unwrap(call(s, "GET", f"/recordings/{note_id}"))


def summarise(note: dict) -> dict:
    return {
        "id": note.get("id"),
        "title": note.get("title"),
        "recorded_at": note.get("recorded_at"),
        "tags": [t["name"] for t in note.get("tags") or []],
    }


def patch_tags(s, note_id: str, names: list[str]) -> dict:
    # web app updateTags(): PATCH /recordings/{id} {"tags": [...]} — full replace
    return summarise(unwrap(call(s, "PATCH", f"/recordings/{note_id}", json={"tags": names})))


def audio_duration_ms(path: Path) -> int:
    if not shutil.which("ffprobe"):
        sys.exit("ffprobe not found (install ffmpeg); the import needs the audio duration")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return int(float(out) * 1000)


def import_audio(s, path: Path, wait: bool) -> dict:
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_AUDIO_MB:
        sys.exit(f"{path.name} is {size_mb:.1f} MB; the import limit is {MAX_AUDIO_MB} MB")
    mime = mimetypes.guess_type(path.name)[0] or ""
    if not mime.startswith("audio/"):
        sys.exit(f"{path.name}: not an audio file by extension ({mime or 'unknown'})")
    duration = audio_duration_ms(path)

    # 1. ask for an upload URL
    signed = call(s, "POST", "/integrations/imports/signed-url",
                  json={"filename": path.name, "type": IMPORT_TYPE_AUDIO, "audio_duration": duration})
    signed = unwrap(signed)
    if not signed.get("url"):
        sys.exit(f"no signed URL in response: {json.dumps(signed)[:300]}")

    # 2. upload the bytes straight to storage (no auth header)
    with path.open("rb") as fh:
        put = requests.put(signed["url"], data=fh, headers={"Content-Type": mime}, timeout=600)
    put.raise_for_status()

    # 3. register the import
    ident = "".join(random.choices(string.ascii_letters + string.digits, k=5))
    form = {
        "filename": (None, path.name),
        "import_id": (None, str(signed["import_id"])),
        "import_identifier": (None, ident),
        "duration": (None, str(duration)),
    }
    created = unwrap(call(s, "POST", "/integrations/imports/new", files=form))
    result = {"import_id": signed["import_id"], "filename": path.name, "duration_ms": duration,
              "response": created}

    # 4. optionally wait for transcription
    if wait:
        for _ in range(60):
            status = unwrap(call(s, "GET", f"/integrations/imports/{signed['import_id']}"))
            rec = status.get("recording")
            if status.get("status") == "failed":
                result["status"] = "failed"
                break
            if rec and status.get("status") == "completed":
                result["note"] = summarise(rec)
                result["transcript_preview"] = (rec.get("transcript") or "")[:300]
                break
            result["status"] = status.get("status")
            time.sleep(10)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tags")
    sub.add_parser("show").add_argument("note_id")
    for name in ("set-tags", "add-tags", "remove-tags"):
        p = sub.add_parser(name)
        p.add_argument("note_id")
        p.add_argument("tags", nargs="*" if name == "set-tags" else "+")
    p = sub.add_parser("import-audio")
    p.add_argument("file", type=Path)
    p.add_argument("--wait", action="store_true", help="poll until the note is transcribed (up to 10 min)")
    a = ap.parse_args()
    s = session()

    if a.cmd == "tags":
        body = call(s, "GET", "/tags")
        tags = body if isinstance(body, list) else body.get("data", [])
        out = [{"id": t["id"], "name": t["name"], "notes": t.get("recordings_count")} for t in tags]
    elif a.cmd == "show":
        out = summarise(get_note(s, a.note_id))
    elif a.cmd == "set-tags":
        out = patch_tags(s, a.note_id, a.tags)
    elif a.cmd in ("add-tags", "remove-tags"):
        current = summarise(get_note(s, a.note_id))["tags"]
        if a.cmd == "add-tags":
            new = current + [t for t in a.tags if t.lower() not in {c.lower() for c in current}]
        else:
            drop = {t.lower() for t in a.tags}
            new = [c for c in current if c.lower() not in drop]
        out = {"before": current, "after": patch_tags(s, a.note_id, new)}
    else:
        out = import_audio(s, a.file, a.wait)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
