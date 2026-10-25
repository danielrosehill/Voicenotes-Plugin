---
name: create-note
description: Create a new text note in Voicenotes, optionally tagged, e.g. "add a note to Voicenotes to follow up with the design team".
---

# Create a Voicenotes text note

Add a text note to the user's Voicenotes account through the bundled `voicenotes` MCP server (tool `create_text_note`).

## Inputs

- The note text. Use the user's words; if they asked you to compose it (a summary, a to-do list), show the text before creating it.
- Optional tags.

## Steps

1. Settle the text and tags. Prefer tags the user already has (check with `list-notes` or a recent search if unsure) so the new note doesn't create near-duplicate tags.
2. Call `create_text_note` with the text and tags.
3. Confirm with the id or title it returns, and the tags applied.

## Notes

- This writes to the user's account. It creates a text note only: the official MCP has no audio upload, and no editing or deleting of existing notes or their tags.
- Connection and sign-in: see `search-notes`.
