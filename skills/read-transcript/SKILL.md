---
name: read-transcript
description: Get the full transcript of a Voicenotes voice note or meeting (by id, or find it first), with title, date and tags.
---

# Read a Voicenotes transcript

Fetch the complete transcript of one note through the bundled `voicenotes` MCP server (tool `get_transcript`).

## Inputs

- A note id, or a description of the note ("my last meeting", "the note about the garden on Tuesday").

## Steps

1. If there is no id, find the note first: `list-notes` for "latest" or date- and tag-based requests, `search-notes` for topic-based ones. When several notes fit, show the candidates (title, date) and ask which one.
2. Call `get_transcript` with the note id.
3. Present title, recorded date, duration if given, and tags, then the transcript. Convert HTML line breaks to newlines. Keep the user's wording exactly as transcribed; do not clean up or summarise unless asked.
4. If the user asked for something derived (summary, action items, a draft), work from the full transcript you fetched, not from the search snippet.

## Notes

- Search can return chunks of imported files (PDFs, documents) whose ids cannot be fetched as notes. If `get_transcript` fails on such an id, say so and use the chunk text from search instead.
- To save the transcript, write it where the user asks; this skill does not store anything by default.
- Connection and sign-in: see `search-notes`.
