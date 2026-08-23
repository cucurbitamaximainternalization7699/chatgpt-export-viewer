# Changelog

## 1.0.0

First public release.

- Reads the official ChatGPT export: single `conversations.json`, sharded `conversations-NNN.json`, or an unpacked directory
- Opens a Privacy Portal export, where the shards sit inside a second ZIP; only the first nesting level is opened, and only for archives that actually hold shards, so a ZIP attached to a conversation is left alone
- Finds shards through `export_manifest.json`, falls back to a filename pattern
- Streams each shard, so a single-line JSON of any size never loads into memory whole
- Rebuilds the visible thread from `current_node` up the `parent` chain, iteratively, with a cycle guard and a fallback to the newest leaf
- Resolves attachments through `conversation_asset_file_names.json`, restores extensions from file signatures, and hard-links them when the source is an unpacked export on the same filesystem
- Renders LaTeX with bundled KaTeX, images inline with a lightbox, tool and reasoning steps in collapsible blocks
- Full-text search over your messages and the model's replies, loaded lazily so the archive opens instantly
- Reports how many referenced attachments are missing from the export, with a per-conversation breakdown
- Dark and light themes, three reading widths, month navigation, per-conversation table of contents
- Muted and warning colours meet the WCAG AA contrast ratio in both themes
- Optional `--seo <base-url>` adds a description, canonical link and Open Graph tags for a public build; a personal archive is generated without them
- 37 edge-case tests covering broken, truncated and unusual exports, including HTML injection and multibyte text split across read boundaries
