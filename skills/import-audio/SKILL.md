---
name: import-audio
description: Upload an audio file (MP3, WAV, M4A…) to Voicenotes to be transcribed as a new note, like Settings → Import. Unofficial.
---

# Import audio into Voicenotes (unofficial)

> **Unofficial.** No official API accepts audio. This skill replays the web app's Settings → Import upload (see `docs/private-api.md`), verified end-to-end 2026-10-25. It can break when Voicenotes changes their app.

Uses Voicenotes as a transcription service: the file becomes a new note with its transcript and an AI title, and counts against the account's recording allowance.

Script: `scripts/vn.py import-audio` (needs `ffprobe` from ffmpeg, for the duration).

## Inputs

- Path(s) to audio files. Audio only, 100 MB or less each (the web app's limit for audio).

## Steps

1. **Token**: as in `edit-tags` (`VOICENOTES_TOKEN` from `copy(JSON.parse(localStorage.auth_token))`).
2. Import, waiting for the transcript:
   ```bash
   uv run --script scripts/vn.py import-audio <file> --wait
   ```
   Returns the import id, the new note's id, title and tags, and the first 300 characters of the transcript. Polls up to 10 minutes; without `--wait` it returns as soon as the upload is registered.
3. For the full transcript, hand the note id to `read-transcript`. To tag it, `edit-tags`.
4. Several files: run one at a time and report each.

## Notes

- Larger than 100 MB: split or compress first (e.g. `ffmpeg -i in.wav -ac 1 -b:a 64k out.mp3`).
- If the account has no recording allowance left, Voicenotes rejects the import; report the error as returned.
- Creates a note in the user's account; to remove it, the user deletes it in the app.
