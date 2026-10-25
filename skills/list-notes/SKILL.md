---
name: list-notes
description: List Voicenotes notes by date range or tag, e.g. "my notes from last week", "everything tagged meeting", "latest note".
---

# List Voicenotes notes

Browse the user's notes filtered by date range and/or tags through the bundled `voicenotes` MCP server (tool `list_notes`).

## Inputs

- A date range (absolute or relative: "last week", "since 1 October"), tag names, or neither (most recent notes).

## Steps

1. Turn relative dates into absolute UTC start and end timestamps. State the range you used in the reply.
2. Call `list_notes` with the range and tags. Tag names must match the user's existing tags; if a tag filter returns nothing, say the tag may be spelled differently rather than concluding there are no notes.
3. Results are paginated. Keep fetching pages until you have enough to answer, or all of them for a "list everything" request. Say how many you fetched and whether more exist.
4. Show one line per note: date, title (or the opening words of the transcript), tags. Offer `read-transcript` for any of them.

## Notes

- Read-only.
- For topic questions ("notes about the move"), `search-notes` is the better tool; listing only filters by date and tag.
- Connection and sign-in: see `search-notes`.
