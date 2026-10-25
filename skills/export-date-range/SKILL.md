---
name: export-date-range
description: Export or back up Voicenotes notes between two dates ("all my notes from March", "last week"), text by default, audio optional. Unofficial.
---

# Export Voicenotes notes from a date range (unofficial)

> **Unofficial.** Uses the voicenotes.com web app's private API (see `docs/private-api.md`); can break when Voicenotes changes their app.

Exports every note recorded between two dates, inclusive. Text only unless the user asks for audio. Reads from the newest note backwards and stops once it passes the start date, so recent ranges are quick.

Script: `scripts/export_selection.py` (`uv run --script`).

## Inputs

- Start and end dates. Turn relative ranges ("last week", "March", "since the 1st") into `YYYY-MM-DD` dates, interpreted in the local time zone, and state them back. Either end may be open.
- Optional tags to narrow it.
- Format: `notes` (one Markdown file per note; default), `single` (one combined Markdown file), or `json`.
- Whether to include the original audio (`--audio`, into `<out>/audio/`).
- Output folder (ask; default `./voicenotes-<from>_to_<to>`).

## Steps

1. **Token.** The user copies it in the DevTools console on a signed-in `https://voicenotes.com/app` tab with `copy(JSON.parse(localStorage.auth_token))` and runs `export VOICENOTES_TOKEN='<paste>'`.
2. **Dry run:**
   ```bash
   uv run --script scripts/export_selection.py --out <dir> --from 2026-03-01 --to 2026-03-31 --dry-run
   ```
   It prints the count, first and last dates and up to 50 titles. Confirm the range looks right.
3. **Export:** the same command without `--dry-run`, plus `--format single|json` and `--audio` as chosen.
4. Report the notes exported, the files written and, with audio, the downloaded and failed counts.

## Notes

- Dates filter on when a note was recorded. The server ignores date parameters, so the script filters locally.
- Audio links expire about 5 minutes after they are issued; the script fetches each one just before its download. Rerunning skips audio already on disk.
- Writes only into the output folder.
