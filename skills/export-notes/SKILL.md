---
name: export-notes
description: Full archive of an entire Voicenotes account, every transcript plus all original audio, for a complete backup. Unofficial.
---

# Export a Voicenotes account (unofficial)

> **Unofficial.** Uses the voicenotes.com web app's own cache and private API, not a documented or supported interface. It can break whenever Voicenotes changes their app. Method confirmed end-to-end on a 6,875-note account on 2026-04-26.

For most exports use `export-text` (transcripts only) or `export-date-range` (a window of dates). This skill is for a complete archive of a large account, audio included.

Two independent halves:

1. **Transcripts and metadata**: read from the web app's IndexedDB cache in the browser. No auth, no network, about 10 seconds.
2. **Audio**: pulled through the private API (`GET /api/recordings/{id}/signed-url`, an S3 link valid about 5 minutes), with the web app's own Bearer token.

Scripts live in the plugin's `scripts/` folder: `dump_indexeddb.js`, `build_archive.py`, `voicenotes_export.py`, `link_audio.py`. The Python ones run with `uv run --script` (or `python3` with `requests` installed).

## Inputs

- Output directory (ask; default `./voicenotes-export`).
- Whether to include audio (the audio is far larger than the text; check free space first).

## Steps

1. **Dump the cache.** The user must be signed in at `https://voicenotes.com/app` and the app must have loaded their notes (scrolling the list once fills the cache). Run `scripts/dump_indexeddb.js` in that tab: with Claude in Chrome, pass the file's contents to `javascript_tool`; otherwise the user pastes it into the DevTools console. It downloads `voicenotes-indexeddb-dump.json` to the browser's download folder. Check the console line `built payload: N records` against the note count the app shows.
2. **Build the archive:**
   ```bash
   uv run --script scripts/build_archive.py --dump <download-folder>/voicenotes-indexeddb-dump.json --out <out>
   ```
   Writes `<out>/catalog.json` and `<out>/notes/YYYY-MM-DD__<id>__<slug>.md` (frontmatter + transcript). Stop here if the user does not want audio.
3. **Get the token (user does this).** In the DevTools console on the app tab: `copy(JSON.parse(localStorage.auth_token))`, then in the shell `export VOICENOTES_TOKEN='<paste>'`. The `JSON.parse` matters: the stored value is wrapped in quotes and the quoted form gets `401 User is Unauthenticated.` Claude in Chrome masks token-like values, so have the user copy it rather than reading it through the browser tools.
4. **Pull audio**, dry run first:
   ```bash
   uv run --script scripts/voicenotes_export.py --out <out> --from-dump <dump> --dry-run
   uv run --script scripts/voicenotes_export.py --out <out> --from-dump <dump>
   ```
   Parallel (8 workers default, about 150 recordings a minute), resumable through `<out>/state.json`: rerun the same command after an interruption. `--from-dump` skips the slow API listing. Without it the script walks the paginated `/api/recordings` (`links.next` until null; there is no total).
5. **Link audio to notes:**
   ```bash
   uv run --script scripts/link_audio.py --out <out>
   ```
   Adds `audio_file` to each note's frontmatter and to `catalog.json`. Idempotent.
6. Report: notes written, audio files downloaded, failures listed in `state.json`, total size.

## Output layout

```
<out>/
├── catalog.json        # one entry per recording
├── notes/              # YYYY-MM-DD__<recording_id>__<slug>.md
├── audio/              # <recording_id>.<ext>, original audio
└── state.json          # resume state for the audio pull
```

## Data storage

Writes only under the output directory the user chose, plus the dump file in the browser's download folder.

## Notes

- The dump and archive are the full account: transcripts, AI "creations", subnotes, tags. Cache entries also carry a per-recording `firebase_token` field; keep the raw dump with the rest of the private export.
- Signed S3 URLs expire in about 5 minutes; the script fetches each one just before its download. Don't batch them.
- A transcript that looks stale in the dump is stale in the app's cache. Opening the note in the app refreshes it; then dump again.
- Imported files (PDFs, documents) are not recordings and have no audio.
