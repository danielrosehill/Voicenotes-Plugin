---
name: edit-tags
description: Add, remove or replace tags on existing Voicenotes notes, and list all tags. Unofficial, via the web app's private API.
---

# Edit tags on Voicenotes notes (unofficial)

> **Unofficial.** The official Voicenotes MCP cannot change tags on an existing note. This skill uses the web app's private API (`PATCH /recordings/{id}`, see `docs/private-api.md`), verified 2026-10-25. It can break when Voicenotes changes their app.

Script: `scripts/vn.py` (run with `uv run --script`).

## Inputs

- Which note(s): an id, or a description to find them with `search-notes` / `list-notes` (both return ids).
- Tags to add, remove, or the full new set.

## Steps

1. **Token.** Needs `VOICENOTES_TOKEN`. The user copies it in the DevTools console on a signed-in `https://voicenotes.com/app` tab with `copy(JSON.parse(localStorage.auth_token))` and runs `export VOICENOTES_TOKEN='<paste>'`.
2. **Use existing tag names.** `vn.py tags` lists every tag with its note count. Match the user's words to an existing name (case-insensitive). Whether an unknown name creates a new tag is untested: if the user wants a new tag, say so and check the result with `show`.
3. **Change the tags:**
   ```bash
   uv run --script scripts/vn.py add-tags <note_id> Idea Work
   uv run --script scripts/vn.py remove-tags <note_id> Work
   uv run --script scripts/vn.py set-tags <note_id> Idea      # replace the whole set; no tags = clear
   ```
   The API replaces the full tag list on every call; `add-tags` and `remove-tags` read the current tags first, so other tags are kept.
4. Report before and after for each note. For a batch, show the list of notes and the change first, run them one by one, and report any that failed.

## Notes

- Writes to the user's account. Only tags change; title and transcript are untouched (checked).
- For tagging a brand-new note, `create-note` (official MCP) takes tags directly.
