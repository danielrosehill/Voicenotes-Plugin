#!/usr/bin/env python3
"""Build a Markdown + catalog archive from an IndexedDB dump.

Pairs with `dump_indexeddb.js`, which produces `voicenotes-indexeddb-dump.json`.
This script reads that JSON and writes:

    <out>/
    ├── catalog.json
    └── notes/
        └── YYYY-MM-DD__<recording_id>__<slug>.md

No network calls, no auth — works fully offline against the cached dump.

Usage:
    python build_archive.py --dump voicenotes-indexeddb-dump.json --out ./voicenotes-export
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


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
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{s}"'


def render_markdown(rec: dict, attachment: Any, tags_top: Any) -> str:
    fm: list[str] = ["---"]
    for k in (
        "id", "recording_id", "parent_id", "title", "recorded_at", "created_at",
        "updated_at", "duration", "public_slug", "is_published",
        "recording_type", "user_id", "user_name",
    ):
        if k in rec:
            fm.append(f"{k}: {yaml_escape(rec.get(k))}")

    tags = rec.get("tags") or tags_top or []
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

    subnotes = rec.get("subnotes") or []
    if subnotes:
        fm.append(f"subnotes_count: {len(subnotes)}")

    attachments = rec.get("attachments") or []
    if attachments:
        fm.append(f"attachments_count: {len(attachments)}")

    fm.append("---")
    fm.append("")

    title = rec.get("title") or "Untitled"
    body: list[str] = [f"# {title}", ""]
    transcript = (rec.get("transcript") or "").strip()
    body.append(transcript or "_(no transcript)_")
    body.append("")

    for c in creations:
        ctype = c.get("type") or c.get("creation_type") or "creation"
        content = (
            c.get("content")
            or c.get("markdown_content")
            or c.get("text")
            or ""
        )
        if content:
            body += ["", f"## Creation: {ctype}", "", str(content).strip(), ""]

    for s in subnotes:
        stitle = s.get("title") or s.get("name") or "Subnote"
        scontent = s.get("content") or s.get("transcript") or s.get("text") or ""
        body += ["", f"## Subnote: {stitle}", "", str(scontent).strip(), ""]

    return "\n".join(fm + body)


def note_filename(rec: dict) -> str:
    rid = rec.get("recording_id") or rec.get("id") or "unknown"
    recorded = (rec.get("recorded_at") or rec.get("created_at") or "")[:10] or "0000-00-00"
    slug = slugify(rec.get("title") or "")
    return f"{recorded}__{rid}__{slug}.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True, type=Path,
                    help="Path to voicenotes-indexeddb-dump.json")
    ap.add_argument("--out", required=True, type=Path,
                    help="Archive output directory")
    ap.add_argument("--limit", type=int, default=0,
                    help="Stop after N records (0 = all). Useful for dry-run.")
    args = ap.parse_args()

    payload = json.loads(args.dump.read_text())
    records = payload.get("records") or []
    if args.limit:
        records = records[: args.limit]

    notes_dir = args.out / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    catalog: list[dict] = []
    seen_ids: set[str] = set()
    skipped = 0

    for entry in records:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        # Two observed shapes in the cache:
        #   (a) wrapper:  {message, recording: {...}, attachment, tags, id}
        #   (b) flat:     {id, recording_id, title, transcript, ...}
        if isinstance(entry.get("recording"), dict):
            rec = entry["recording"]
            attachment = entry.get("attachment")
            tags_top = entry.get("tags")
        else:
            rec = entry
            attachment = entry.get("attachment")
            tags_top = entry.get("tags")

        rid = rec.get("recording_id") or str(rec.get("id"))
        if not rid or rid in seen_ids:
            skipped += 1
            continue
        seen_ids.add(rid)

        md_name = note_filename(rec)
        md_path = notes_dir / md_name
        md_path.write_text(render_markdown(rec, attachment, tags_top))

        catalog.append({
            "recording_id": rid,
            "id": rec.get("id"),
            "title": rec.get("title"),
            "recorded_at": rec.get("recorded_at"),
            "duration": rec.get("duration"),
            "tags": [t.get("name") if isinstance(t, dict) else t
                     for t in (rec.get("tags") or entry.get("tags") or [])],
            "note_file": str(md_path.relative_to(args.out)),
        })

    catalog_path = args.out / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))

    total_dur = sum(int((r.get("recording") or {}).get("duration") or 0) for r in records)
    print(f"Wrote {len(catalog)} notes to {notes_dir}")
    print(f"Catalog: {catalog_path}")
    if skipped:
        print(f"Skipped: {skipped} (missing recording payload or duplicate id)")
    print(f"Total duration in dump: {total_dur}s ({total_dur/3600:.1f}h)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
