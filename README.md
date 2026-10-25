# Voicenotes Plugin

![Unofficial](https://img.shields.io/badge/status-UNOFFICIAL-red) ![Not affiliated with Voicenotes](https://img.shields.io/badge/not%20affiliated-Voicenotes-lightgrey) ![Early release](https://img.shields.io/badge/version-0.4.0%20early-orange)

> [!WARNING]
> **Unofficial, community plugin. Not made, endorsed or supported by Voicenotes.** The core skills use Voicenotes' official MCP server. Skills marked *unofficial* below go through the web app's private API and local cache, which Voicenotes does not document and can change at any time.

Use your [Voicenotes](https://voicenotes.com) notes from Claude Code: search them, read full transcripts, list them by date or tag, add text notes, edit tags, import audio for transcription and export everything.

> **Early release.** Unofficial skills replay calls the voicenotes.com web app makes; they were verified on 2026-10-25 and may break. Endpoint notes: [docs/private-api.md](docs/private-api.md). Plans: [docs/roadmap.md](docs/roadmap.md).

## Skills

Official MCP:

- `search-notes`: semantic search across your notes.
- `read-transcript`: the full transcript of a voice note or meeting.
- `list-notes`: notes filtered by date range or tags.
- `create-note`: a new text note, optionally tagged.

Unofficial (private API / browser cache):

- `export-text`: transcripts only, no audio, for all notes or chosen tags or notes; one file per note, one combined file, or JSON.
- `export-date-range`: every note between two dates, text by default, audio optional.
- `export-notes`: full archive of the whole account with all original audio (for complete backups of large accounts).
- `edit-tags`: add, remove or replace tags on existing notes; list all tags.
- `import-audio`: upload an audio file to be transcribed as a new note (Voicenotes as a transcription service).

The unofficial skills need the web app's token: in the DevTools console on a signed-in `https://voicenotes.com/app` tab run `copy(JSON.parse(localStorage.auth_token))`, then `export VOICENOTES_TOKEN='<paste>'`. Treat it like a password.

## MCP server

The plugin bundles the official Voicenotes MCP server (`.mcp.json`):

```
https://api.voicenotes.com/mcp   (HTTP, OAuth)
```

After installing, run `/mcp`, select `voicenotes`, and choose **Authenticate**. A browser sign-in opens; there is no API key. If asked for a client ID or secret, leave both blank. Voicenotes' setup guide: <https://help.voicenotes.com/en/articles/14336494-how-to-use-voicenotes-mcp-server-in-claude>.

## Installation

```bash
claude plugins marketplace add danielrosehill/Claude-Code-Plugins
claude plugins install voicenotes@danielrosehill
```

## License

MIT
