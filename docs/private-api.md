# Voicenotes private API (unofficial)

The endpoints the voicenotes.com web app calls, as used by this plugin's unofficial skills. Undocumented by Voicenotes; they can change without notice. Read from the web app's JavaScript bundle (`/_nuxt/CD8tmtMZ.js`, `/_nuxt/BK9jNCFM.js`) and verified live on 2026-10-25 unless marked otherwise.

## Auth

- Base: `https://api.voicenotes.com/api`
- Header: `Authorization: Bearer <token>`, where `<token>` is `JSON.parse(localStorage.auth_token)` on a signed-in `https://voicenotes.com/app` tab. The raw localStorage value is wrapped in quotes; sending it as-is returns `401 {"message":"User is Unauthenticated."}`.
- The Claude in Chrome tools mask token-shaped values in their output. Keep the token in a page variable when calling from the page, or have the user copy it for shell use.

## Notes and tags

| Call | Body | Result | Verified |
|---|---|---|---|
| `GET /recordings?page=N` | | `{data:[…], links:{next}}`, 10 per page, no total. Newest first (by `created_at` and `recorded_at`). Items carry the full transcript and `creations`, same as the single-note call. Date query parameters (`from`/`to`, `date_from`/`date_to`) are ignored. | yes |
| `GET /recordings/{id}` | | `{data:{…}}` full note, `tags` = array of tag objects | yes |
| `PATCH /recordings/{id}` | `{"tags":["Name", …]}` | 200, the updated note (not wrapped in `data`). **Full replace**; `[]` clears. Title and transcript unchanged. | yes, add / replace / clear |
| `GET /tags` | | array of `{id, name, keywords, is_pinned, emoji, recordings_count, …}` | yes |
| `PATCH /recordings/{id}` | `{"title","transcript","note","tags"}` | web app `updateNote()` | no |
| `POST /tags` · `PATCH /tags/{id}` · `DELETE /tags/{id}` · `PATCH /tags/{id}/pin` · `POST /tags/{id}/attach` | | tag management | no |

Untested: whether `PATCH` with a tag name that does not exist yet creates the tag.

## Audio import (Settings → Import)

1. `POST /integrations/imports/signed-url` with JSON `{"filename": "<name>", "type": 3, "audio_duration": <ms>}`. `type`: 1 = `.md`, 2 = PDF, 3 = audio, 4 = other. Returns 201 `{message, url, import_id}`; `url` is a pre-signed S3 PUT on `voicenotesbucket.s3.us-west-2.amazonaws.com`.
2. `PUT <url>` with the raw bytes and `Content-Type` = the file's MIME type. No auth header. 200.
3. `POST /integrations/imports/new`, multipart: `filename`, `import_id`, `import_identifier` (any 5-char random string), `duration` (ms). 201 `{message, import, import_identifier, recording}`.
4. Poll `GET /integrations/imports/{import_id}` → `{data:{import_id, filename, status, recording, …}}` until `status` is `completed`. A 3-second WAV completed in under 10 s; the note came back with `recording_type` 6, an AI title and the transcript.

Limits enforced by the web app before step 1: audio ≤ 100 MB, other file types ≤ 50 MB (the help centre says 50 MB for everything; the bundle checks 100 MB when the file has a duration), and the account must have recording allowance left (`can_record_more`).

## Also in the bundle, not used

- Recording upload as a native voice note: `GET /recordings/signed-url` → `PUT` (`audio/mpeg`) → `POST /recordings/new` multipart with `upload_id`, `duration`, `recording_identifier`, `device_info`, `recording_type`.
- `GET /recordings/{id}/signed-url`: download link for a note's audio (used by `export-notes`).
- `POST /recordings/{id}/transcript/update`, `PATCH /recordings/{id}/star`, `POST /recordings/{id}/move`.
