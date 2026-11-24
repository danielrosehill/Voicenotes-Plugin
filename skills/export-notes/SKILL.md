---
name: export-notes
description: Full archive of an entire Voicenotes account, every transcript plus all original audio, for a complete backup. Unofficial.
---

# Export a Voicenotes account (unofficial)

> **Unofficial.** Uses the voicenotes.com web app's own cache and private API, not a documented or supported interface. It can break whenever Voicenotes changes their app. Method confirmed end-to-end on a 6,875-note account on 2026-04-26.

For most exports use `export-text` (transcripts only) or `export-date-range` (a window of dates). This skill is for a complete archive of a large account, audio included.

Script: `scripts/full_export.py` (`uv run --script`). Resumable and verified: reads every page of the API listing, downloads each note's original audio, checks size and media type (and duration, with `ffprobe` installed), then re-hashes everything into `report.json`. Tests: `tests/test_full_export.py`.

## Inputs

- Output directory, on a disk with room for the audio (one 5,500-note account: 8.9 GB). Prefer an always-on machine.

## Steps

1. **Optional cache dump.** On a signed-in `https://voicenotes.com/app` tab, run `scripts/dump_indexeddb.js` (Claude in Chrome `javascript_tool`, or the DevTools console). It needs no token and works as a text-only export by itself (`build_archive.py`). Passed as `--dump`, it adds notes the API listing misses.
2. **Token (the user does this).** DevTools console on the app tab: `copy(JSON.parse(localStorage.auth_token))`. Pass it as `VOICENOTES_TOKEN` or on stdin with `--token-stdin`. It is never written to disk.
3. **Trial**, newest 20 notes, in a scratch directory: `uv run --script scripts/full_export.py --out <scratch> --limit 20`. Read `report.json`.
4. **Full run**: `uv run --script scripts/full_export.py --out <out> [--dump <dump>]`. Exit 0 = complete and verified; 1 = some failed, run again; 3 = token rejected, get a new one and run again.
5. Report from `report.json`: notes, audio counts by status, `problems`, `duration_mismatches`. `no_audio` means the API said 404 (typed or imported notes); `missing` means a link existed but the file is gone.
   **No token option** (the login stays in the browser): `full_export.py --listing` with the cache dump's records, `--pending > ids.json`, start `scripts/browser_bridge.py`, then run `scripts/browser_bridge.js` in the signed-in tab. Firefox asks to let voicenotes.com reach apps on this device: the user decides, never click it for them. The API rate-limits (429) at about 8 parallel calls (seen 2026-11-24); the script makes one call at a time, about 58 a minute. When it finishes, merge `WORK/pages/*.json` with `--listing`, then `--pending` and repeat if any are left.
6. Later integrity check, offline: `full_export.py --out <out> --verify`.

## Output layout

```
<out>/
├── notes.jsonl      # full note records, oldest first (firebase_token removed)
├── audio/           # <recording_id>.<ext>, original audio
├── manifest.jsonl   # note -> audio file, bytes, sha256, seconds
├── report.json      # verification result
└── state.db         # resume state
```

## Data storage

Writes only under the output directory the user chose, plus the dump file in the browser's download folder.

## Notes

- The dump and archive are the full account: transcripts, AI "creations", subnotes, tags. Cache entries also carry a per-recording `firebase_token` field; keep the raw dump with the rest of the private export.
- An older run of `voicenotes_export.py` that was interrupted left 1,368 of 6,875 notes without audio and reported nothing afterwards; `full_export.py` replaces it.
- `transcript` holds the raw transcript; transformations are separate, in `creations` (only in the live API, not in the cache). No endpoint for the pre-edit text of a hand-edited transcript was found.
- Signed S3 URLs expire in about 11 minutes (2026-11-24; about 5 earlier); the script fetches each one just before its download. Don't batch them.
- A transcript that looks stale in the dump is stale in the app's cache. Opening the note in the app refreshes it; then dump again.
- Imported files (PDFs, documents) are not recordings and have no audio.
