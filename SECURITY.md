# Security

## What this tool does with your data

Everything happens on your machine. The generator reads the export you point it at and writes HTML next to it. It makes no network requests, sends no telemetry, and has no update check.

The generated site is equally offline. KaTeX is bundled in `assets/katex`, and the generator never emits a tag that loads something from the internet: every `src` points inside your own `files/` folder, and markdown images from your conversations become links rather than embedded remote images.

External addresses do appear in the output, because links you and the model exchanged are kept clickable. They are only followed if you click them. You can check that nothing loads on its own:

```bash
grep -rEo '(src|url\()="?https?://[^")]*' your-archive/site/ --include="*.html" --include="*.js" --include="*.css"
```

An empty result means no external resource is fetched when the page opens. Searching for `https://` alone will match the links inside your conversations, which is expected.

## What ends up in the output

The generated site contains your conversations in plain HTML, plus a search index that includes the text of your messages and the model's replies. Treat the output folder exactly like the export itself: it is your full history in readable form.

If you publish the site anywhere, remember that `site/search-text.js` holds the searchable text of every conversation.

## Reporting a vulnerability

Open a private security advisory through the Security tab of this repository. Please do not attach exports or personal data to any report.
