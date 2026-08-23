# Contributing

## The most useful thing you can report

The export format changes without notice and without documentation. Shards appeared in 2026, attachments lost their extensions in May 2026, `status` and `weight` vanished from messages in July 2026. Every one of those broke tools in the wild.

If your export looks different from what this tool expects, open a **Export format problem** issue with the archive listing (`unzip -l`) and the console output. Never attach the export itself: it is your entire history.

## Running the tests

No dependencies, no test runner to install:

```bash
python3 tests/test_exports.py
```

Thirty-seven cases, under two seconds. They build deliberately broken exports (sharded, truncated, cyclic, nested, missing `current_node`) and check that the generator survives.

## Trying changes without your own data

```bash
python3 tests/make_demo_export.py demo-export.zip
python3 build_site.py demo-export.zip
```

The generator in `tests/make_demo_export.py` produces 32 invented conversations with images, math, code and a deliberately missing attachment.

## Code style

- `build_site.py` has no dependencies and stays that way. Pillow is optional and guarded by a try/except.
- The generated site makes no network requests. KaTeX is bundled in `assets/katex`; nothing may be pulled from a CDN.
- Everything in the interface is English. Conversation content is shown in whatever language it was written.
- Add a test for anything the parser has to tolerate. A new field, a new content type, a new asset naming scheme: all of that belongs in `tests/test_exports.py`.

## What this project does not do

It reads exports, it does not fetch anything from ChatGPT. There is no scraping code here and pull requests adding it will not be merged.
