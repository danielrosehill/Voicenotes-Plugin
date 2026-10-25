#!/usr/bin/env python3
"""Link downloaded audio files back into note frontmatter + catalog.

After `voicenotes_export.py` finishes, every note in `notes/` and every audio
file in `audio/` shares the same `<recording_id>` stem — so the association is
already lossless. This script makes it explicit:

  - Adds `audio_file: "audio/<recording_id>.<ext>"` to each note's YAML
    frontmatter (or removes it if no audio exists for that recording).
  - Adds `audio_file` and `audio_size_bytes` to each catalog.json entry.

Idempotent. Safe to run multiple times.

Usage:
    python link_audio.py --out ./voicenotes-export
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


# Filenames look like: YYYY-MM-DD__<recording_id>__<slug>.md
NOTE_RID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}__([^_]+)__")


def find_audio_path(audio_dir: Path, rid: str) -> Path | None:
    matches = list(audio_dir.glob(f"{rid}.*"))
    return matches[0] if matches else None


def update_frontmatter(md_path: Path, audio_rel: str | None) -> bool:
    text = md_path.read_text()
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---\n", 4)
    if end == -1:
        return False
    fm_block = text[4:end]
    body = text[end + 5 :]

    lines = [ln for ln in fm_block.split("\n") if not ln.startswith("audio_file:")]
    if audio_rel:
        # insert after `id:` / `recording_id:` / first line for visibility
        insert_at = 0
        for i, ln in enumerate(lines):
            if ln.startswith("recording_id:") or ln.startswith("id:"):
                insert_at = i + 1
        lines.insert(insert_at, f'audio_file: "{audio_rel}"')

    new_text = "---\n" + "\n".join(lines) + "\n---\n" + body
    if new_text != text:
        md_path.write_text(new_text)
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path,
                    help="Export root (the dir holding notes/ and audio/)")
    args = ap.parse_args()

    out: Path = args.out
    notes_dir = out / "notes"
    audio_dir = out / "audio"
    catalog_path = out / "catalog.json"

    if not notes_dir.is_dir():
        print(f"no notes dir: {notes_dir}")
        return 2
    audio_dir.mkdir(exist_ok=True)

    # 1) Walk notes, link to audio (or unlink if missing)
    note_count = 0
    linked = 0
    unlinked = 0
    rewritten = 0
    rid_to_audio: dict[str, str] = {}

    for md in notes_dir.glob("*.md"):
        m = NOTE_RID_RE.match(md.name)
        if not m:
            continue
        rid = m.group(1)
        note_count += 1
        audio_path = find_audio_path(audio_dir, rid)
        if audio_path:
            rel = str(audio_path.relative_to(out))
            rid_to_audio[rid] = rel
            if update_frontmatter(md, rel):
                rewritten += 1
            linked += 1
        else:
            if update_frontmatter(md, None):
                rewritten += 1
            unlinked += 1

    # 2) Catalog: add audio_file + audio_size_bytes when present
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text())
        for entry in catalog:
            rid = entry.get("recording_id")
            rel = rid_to_audio.get(rid)
            if rel:
                entry["audio_file"] = rel
                entry["audio_size_bytes"] = (out / rel).stat().st_size
            else:
                entry.pop("audio_file", None)
                entry.pop("audio_size_bytes", None)
        catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
        print(f"Catalog updated: {catalog_path}")

    print(f"Notes scanned: {note_count}")
    print(f"  with audio:  {linked}")
    print(f"  no audio:    {unlinked}")
    print(f"  rewritten:   {rewritten}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
