# Roadmap and findings

Status: **early release.** v0.1.0 (2026-10-25) wrapped the four official MCP tools. v0.2.0 (2026-10-25) adds the unofficial `export-notes` skill, ported from a private exporter whose method was confirmed end-to-end on 2026-04-26 (IndexedDB cache dump for transcripts; `GET /api/recordings/{id}/signed-url` with the unwrapped `localStorage.auth_token` for audio). v0.3.0 (2026-10-25) adds unofficial `edit-tags` and `import-audio`, both verified live.

## Findings (2026-10-25)

Confirmed:

- Official MCP endpoint: `https://api.voicenotes.com/mcp`, streamable HTTP. Unauthenticated `initialize` returns `401` with `WWW-Authenticate: Bearer realm="mcp", resource_metadata="https://api.voicenotes.com/.well-known/oauth-protected-resource/mcp"`. The protected-resource metadata names `https://api.voicenotes.com` as authorization server, scope `mcp:use`. OAuth with dynamic client registration; no API key.
- Tools, per the Voicenotes help centre (https://help.voicenotes.com/en/articles/14336494-how-to-use-voicenotes-mcp-server-in-claude): `search_notes`, `list_notes`, `get_transcript`, `create_text_note`. The help page does not publish their input schemas, so the skills describe intent and leave argument names to the live schema.
- No Claude Code plugin for Voicenotes existed (GitHub repo and code search, the Daniel Rosehill marketplaces and skill catalogue, web search).
- Voicenotes publishes an official skill for OpenClaw (`voicenotes-official` on ClawHub, mirrored in e.g. `nordeim/openclaw-curated-skills`). It calls a separate key-authenticated REST surface, `https://api.voicenotes.com/api/integrations/open-claw/...` (`search/semantic`, `recordings`, `recordings/{uuid}`, `recordings/new`), with the same four operations. Not used here: it needs an API key from an OpenClaw integration and its setup targets OpenClaw.

Verified 2026-10-25 (v0.3.0), details in `private-api.md`:

- **Tag editing**: `PATCH /recordings/{id}` `{"tags":[names]}`, full replace. Tested add, replace and clear on a scratch note.
- **Audio import**: signed-url → S3 PUT → `imports/new` → poll. Tested with a 3 s WAV, transcribed in under 10 s.

## Next

1. Check whether `PATCH` with an unknown tag name creates the tag.
2. Title and transcript editing (`updateNote`, `transcript/update`) if wanted.
3. Record the official MCP tool input schemas in `reference/` once connected.
