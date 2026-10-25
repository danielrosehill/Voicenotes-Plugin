#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""Selective Voicenotes export: a date range, some tags or some notes; text by default.

Unofficial: uses the web app's private API (see docs/private-api.md).
Checked 2026-10-25: GET /recordings pages run newest first, each item carries
the full transcript and AI creations, and the server ignores date query
parameters, so the date filter is applied here and paging stops once notes
are older than --from.

Auth: export VOICENOTES_TOKEN='<JSON.parse(localStorage.auth_token)>'

Usage:
    export_selection.py --out DIR [--from YYYY-MM-DD] [--to YYYY-MM-DD]
                        [--tag NAME ...] [--id NOTE_ID ...]
                        [--format notes|single|json] [--audio] [--dry-run]

    --from/--to   inclusive calendar dates in local time (either may be omitted)
    --tag         keep notes carrying any of these tags (case-insensitive)
    --id          export exactly these notes (skips listing)
    --format      notes  = one Markdown file per note (default)
                  single = one combined Markdown file, oldest first
                  json   = one JSON array of the raw note objects
    --audio       also download each note's original audio into DIR/audio/
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from voicenotes_export import (  # noqa: E402  (sibling script)
    API_BASE, PAGE_DELAY, audio_extension, build_session, download_audio,
    get_signed_url, note_filename, render_markdown, request_with_retry,
)
import os  # noqa: E402


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def local_bound(d: str, end: bool) -> datetime:
    day = date.fromisoformat(d)
    t = dtime.max if end else dtime.min
    return datetime.combine(day, t).astimezone().astimezone(timezone.utc)


def clean_html(text: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", text or "")
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def cleaned(rec: dict) -> dict:
    rec = dict(rec)
    rec["transcript"] = clean_html(rec.get("transcript") or "")
    rec["creations"] = [
        {**c, "content": clean_html(str(c.get("markdown_content") or c.get("content") or ""))}
        for c in rec.get("creations") or []
    ]
    return rec


def tag_names(rec: dict) -> set[str]:
    return {(t.get("name") if isinstance(t, dict) else str(t)).lower() for t in rec.get("tags") or []}


def select(session, start: datetime | None, end: datetime | None, tags: set[str]) -> tuple[list[dict], int]:
    out, url, pages = [], f"{API_BASE}/recordings", 0
    while url:
        body = request_with_retry(session, "GET", url).json()
        pages += 1
        stop = False
        for rec in body.get("data", []):
            created = parse_ts(rec.get("created_at"))
            recorded = parse_ts(rec.get("recorded_at")) or created
            # recorded_at <= created_at holds, so once created_at is before the
            # start nothing later in the list can fall inside the range
            if start and created and created < start:
                stop = True
                break
            if end and recorded and recorded > end:
                continue
            if start and recorded and recorded < start:
                continue
            if tags and not (tag_names(rec) & tags):
                continue
            out.append(rec)
        if pages % 20 == 0:
            print(f"  ...{pages} pages read, {len(out)} selected", file=sys.stderr)
        url = None if stop else (body.get("links") or {}).get("next")
        if url:
            time.sleep(PAGE_DELAY)
    return out, pages


def fetch_ids(session, ids: list[str]) -> list[dict]:
    out = []
    for rid in ids:
        body = request_with_retry(session, "GET", f"{API_BASE}/recordings/{rid}").json()
        out.append(body.get("data", body))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--id", dest="ids", action="append", default=[])
    ap.add_argument("--format", choices=["notes", "single", "json"], default="notes")
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    token = os.environ.get("VOICENOTES_TOKEN", "").strip().strip('"')
    if not token:
        sys.exit("set VOICENOTES_TOKEN (DevTools: copy(JSON.parse(localStorage.auth_token)))")
    session = build_session(token)

    start = local_bound(a.start, end=False) if a.start else None
    end = local_bound(a.end, end=True) if a.end else None
    if a.ids:
        notes, pages = fetch_ids(session, a.ids), 0
    else:
        notes, pages = select(session, start, end, {t.lower() for t in a.tag})
    notes.sort(key=lambda r: r.get("recorded_at") or r.get("created_at") or "")

    summary = {
        "selected": len(notes),
        "pages_read": pages,
        "range": [a.start, a.end],
        "tags": a.tag,
        "first": notes[0].get("recorded_at") if notes else None,
        "last": notes[-1].get("recorded_at") if notes else None,
        "format": a.format,
        "audio": a.audio,
        "out": str(a.out),
    }
    if a.dry_run or not notes:
        summary["dry_run"] = a.dry_run
        summary["titles"] = [f"{(n.get('recorded_at') or '')[:10]}  {n.get('title') or '(untitled)'}" for n in notes[:50]]
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    a.out.mkdir(parents=True, exist_ok=True)
    if a.format == "notes":
        notes_dir = a.out / "notes"
        notes_dir.mkdir(exist_ok=True)
        for n in notes:
            (notes_dir / note_filename(n)).write_text(render_markdown(cleaned(n)), encoding="utf-8")
    elif a.format == "single":
        label = f"{a.start or 'start'}_to_{a.end or 'latest'}"
        parts = [f"# Voicenotes export: {a.start or 'beginning'} to {a.end or 'latest'}", "",
                 f"{len(notes)} notes. Exported {datetime.now().astimezone():%Y-%m-%d %H:%M %Z}.", ""]
        for n in notes:
            md = render_markdown(cleaned(n)).split("---\n", 2)[-1].lstrip()  # drop per-note frontmatter
            tags = ", ".join(sorted(t.get("name") for t in n.get("tags") or [] if isinstance(t, dict)))
            meta = f"*{(n.get('recorded_at') or '')[:16].replace('T', ' ')} UTC*" + (f" · tags: {tags}" if tags else "")
            heading, _, rest = md.partition("\n")
            parts += ["---", "", "#" + heading, "", meta, rest.replace("\n## Creation:", "\n### Creation:"), ""]
        summary["file"] = str(a.out / f"voicenotes_{label}.md")
        Path(summary["file"]).write_text("\n".join(parts), encoding="utf-8")
    else:
        summary["file"] = str(a.out / "voicenotes.json")
        Path(summary["file"]).write_text(json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8")

    if a.audio:
        audio_dir, got, failed = a.out / "audio", 0, []
        for n in notes:
            rid = n.get("recording_id") or n.get("id")
            if not n.get("has_audio", True) or (n.get("duration") or 0) == 0:
                continue
            if any(audio_dir.glob(f"{rid}.*")):
                got += 1
                continue
            url = get_signed_url(session, rid)  # valid ~5 min: fetch right before download
            if not url:
                failed.append(rid)
                continue
            try:
                download_audio(url, audio_dir / f"{rid}.{audio_extension(url)}")
                got += 1
            except Exception:
                failed.append(rid)
        summary["audio_files"] = got
        summary["audio_failed"] = failed

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
