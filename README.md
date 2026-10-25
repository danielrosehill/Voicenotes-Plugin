# Voicenotes Plugin

Use your [Voicenotes](https://voicenotes.com) notes from Claude Code: search them, read full transcripts, list them by date or tag, and add text notes.

> **Early placeholder (v0.1.0).** This plugin covers the basic operations of the official Voicenotes MCP server. Tag editing and audio import are not in that server and are not covered yet; see [docs/roadmap.md](docs/roadmap.md).

## Skills

- `search-notes`: semantic search across your notes.
- `read-transcript`: the full transcript of a voice note or meeting.
- `list-notes`: notes filtered by date range or tags.
- `create-note`: a new text note, optionally tagged.

## MCP server

The plugin bundles the official Voicenotes MCP server (`.mcp.json`):

```
https://api.voicenotes.com/mcp   (HTTP, OAuth)
```

After installing, run `/mcp`, select `voicenotes`, and choose **Authenticate**. A browser sign-in opens; there is no API key. If asked for a client ID or secret, leave both blank. Voicenotes' setup guide: <https://help.voicenotes.com/en/articles/14336494-how-to-use-voicenotes-mcp-server-in-claude>.

This plugin is not affiliated with Voicenotes.

## Installation

```bash
claude plugins marketplace add danielrosehill/Claude-Code-Plugins
claude plugins install voicenotes@danielrosehill
```

## License

MIT
