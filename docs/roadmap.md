# Roadmap and findings

Status: **early placeholder.** v0.1.0 (2026-10-25) wrapped the four official MCP tools. v0.2.0 (2026-10-25) adds the unofficial `export-notes` skill, ported from a private exporter whose method was confirmed end-to-end on 2026-04-26 (IndexedDB cache dump for transcripts; `GET /api/recordings/{id}/signed-url` with the unwrapped `localStorage.auth_token` for audio).

## Findings (2026-10-25)

Confirmed:

- Official MCP endpoint: `https://api.voicenotes.com/mcp`, streamable HTTP. Unauthenticated `initialize` returns `401` with `WWW-Authenticate: Bearer realm="mcp", resource_metadata="https://api.voicenotes.com/.well-known/oauth-protected-resource/mcp"`. The protected-resource metadata names `https://api.voicenotes.com` as authorization server, scope `mcp:use`. OAuth with dynamic client registration; no API key.
- Tools, per the Voicenotes help centre (https://help.voicenotes.com/en/articles/14336494-how-to-use-voicenotes-mcp-server-in-claude): `search_notes`, `list_notes`, `get_transcript`, `create_text_note`. The help page does not publish their input schemas, so the skills describe intent and leave argument names to the live schema.
- No Claude Code plugin for Voicenotes existed (GitHub repo and code search, the Daniel Rosehill marketplaces and skill catalogue, web search).
- Voicenotes publishes an official skill for OpenClaw (`voicenotes-official` on ClawHub, mirrored in e.g. `nordeim/openclaw-curated-skills`). It calls a separate key-authenticated REST surface, `https://api.voicenotes.com/api/integrations/open-claw/...` (`search/semantic`, `recordings`, `recordings/{uuid}`, `recordings/new`), with the same four operations. Not used here: it needs an API key from an OpenClaw integration and its setup targets OpenClaw.

Not yet verified:

- **Tag and title editing.** Not in the official MCP or the OpenClaw API. A community server (`mayankbohradev/voicenotes-mcp`) uses the web app's private API: `PATCH /api/recordings/{id}` with title and/or tags (tags replace the whole set), plus `GET/POST/PATCH/DELETE /api/tags`. Auth there is the web app's Bearer token: `JSON.parse(localStorage.auth_token)` on a logged-in voicenotes.com tab (the raw localStorage value is JSON-quoted and gives 401). Untested by this plugin.
- **Audio upload / using Voicenotes as a transcription service.** No documented route. The app has Settings → Import (MP3, WAV, M4A, up to 50 MB; https://help.voicenotes.com/en/articles/15391500-how-to-import-files-into-voicenotes), but its upload call is undocumented.

## Next

1. `edit-tags` skill: verify `PATCH /api/recordings/{id}` against a real account in a browser session, then decide whether a private-API skill belongs in a public plugin (it would be marked unofficial).
2. Capture the Settings → Import network calls in a browser session to see whether audio import can be scripted.
3. Record the live MCP tool input schemas in `reference/` once connected.
