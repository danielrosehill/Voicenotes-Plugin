# Voicenotes Plugin

![Unofficial](https://img.shields.io/badge/status-UNOFFICIAL-red) ![Not affiliated with Voicenotes](https://img.shields.io/badge/not%20affiliated-Voicenotes-lightgrey) ![Early placeholder](https://img.shields.io/badge/version-0.2.0%20early-orange)

> [!WARNING]
> **Unofficial, community plugin. Not made, endorsed or supported by Voicenotes.** The core skills use Voicenotes' official MCP server. Skills marked *unofficial* below go through the web app's private API and local cache, which Voicenotes does not document and can change at any time.

Use your [Voicenotes](https://voicenotes.com) notes from Claude Code: search them, read full transcripts, list them by date or tag, and add text notes.

> **Early placeholder.** Tag editing and audio import are not covered yet; see [docs/roadmap.md](docs/roadmap.md).

## Skills

Official MCP:

- `search-notes`: semantic search across your notes.
- `read-transcript`: the full transcript of a voice note or meeting.
- `list-notes`: notes filtered by date range or tags.
- `create-note`: a new text note, optionally tagged.

Unofficial (private API / browser cache):

- `export-notes`: bulk export of the whole account, transcripts to Markdown plus original audio. Scripts in `scripts/`; needs a signed-in voicenotes.com tab and, for audio, the web app's own token.

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
