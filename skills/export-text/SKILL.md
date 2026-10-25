---
name: export-text
description: Export Voicenotes transcripts as text only (no audio) to Markdown, one file or one per note, for all notes or chosen ones. Unofficial.
---

# Export Voicenotes notes as text (unofficial)

> **Unofficial.** Uses the voicenotes.com web app's private API (see `docs/private-api.md`); can break when Voicenotes changes their app.

Text-only export: transcripts, titles, dates, tags and AI creations (summaries etc.), with no audio. HTML from the transcripts is turned into plain text. For a date window use `export-date-range`; for a full archive including audio, `export-notes`.

Script: `scripts/export_selection.py` (`uv run --script`).

## Inputs

- Which notes: all, some tags, specific note ids, or a date range.
- Output folder (ask; default `./voicenotes-text`).
- Format: `notes` (one Markdown file per note, with YAML frontmatter; default), `single` (one combined Markdown file, oldest first, good for reading or pasting into a document), or `json`.

## Steps

1. **Token.** The user copies it in the DevTools console on a signed-in `https://voicenotes.com/app` tab with `copy(JSON.parse(localStorage.auth_token))` and runs `export VOICENOTES_TOKEN='<paste>'`.
2. **Dry run first**: it prints how many notes match and their dates and titles.
   ```bash
   uv run --script scripts/export_selection.py --out <dir> [--tag Idea] [--id <note_id> ...] --dry-run
   ```
3. Show the count and range; then run the same command without `--dry-run`, adding `--format single` or `--format json` if wanted.
4. Report the folder or file and the number of notes.

## Notes

- With no date or tag filter it reads the whole account, about 10 notes per API page, newest first. Large accounts take minutes; say so before starting.
- A handful of notes needs no token: fetch each with `read-transcript` (official MCP) and write the files directly.
- Writes only into the output folder.
