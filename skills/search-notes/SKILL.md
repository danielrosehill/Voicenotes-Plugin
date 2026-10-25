---
name: search-notes
description: Search Voicenotes notes by meaning ("what did I say about X") with the official MCP; returns matching notes and transcript chunks.
---

# Search Voicenotes notes

Semantic search over the user's Voicenotes notes, via the bundled `voicenotes` MCP server (tool `search_notes`).

## Inputs

- What the user is looking for, in their own words. Pass it as a natural-language query, not keywords; the search is semantic.

## Steps

1. Call `search_notes` with the query. If the tool is missing or returns an auth error, follow "Connection" below.
2. Results are ordered by relevance. A hit can be a whole note or a chunk of a longer note. Each carries an id, title, transcript text, tags and a creation date.
3. Report the top hits: title (or the first words of the transcript when the title is empty), date, tags, and the passage that matched. Say which hits are chunks of longer notes.
4. If the user wants the whole note, hand the id to `read-transcript`.
5. If nothing relevant comes back, rephrase once (broader, or with a synonym) before saying there is no match. To narrow by date or tag instead of meaning, use `list-notes`.

## Connection

The plugin registers `https://api.voicenotes.com/mcp` (HTTP, OAuth). On first use the user runs `/mcp`, picks `voicenotes`, and chooses Authenticate; a browser sign-in follows. There is no API key. If the client asks for a client ID or secret, leave both blank (the server uses dynamic client registration).

## Notes

- Transcripts may contain HTML (`<br>`, `<b>`). Render it as plain text or Markdown.
- Read-only. Nothing is changed in the account.
