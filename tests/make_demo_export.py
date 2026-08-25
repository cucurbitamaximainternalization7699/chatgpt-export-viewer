"""Generate a fake ChatGPT export for demos, screenshots and tests.

Usage:
    python3 tests/make_demo_export.py [output.zip] [--conversations N]

The result mirrors the official export layout: sharded conversations,
extension-less .dat assets and an asset name index.

The archive is built to look like a real one that has been in use for years:
several hundred conversations spread over three years, ending today, with code,
maths, tables, images, reasoning steps and one attachment the export lost.
"""

import datetime
import io
import json
import os
import random
import sys
import zipfile

OUT = 'demo-export.zip'
TOTAL = 450
argv = sys.argv[1:]
if '--conversations' in argv:
    at = argv.index('--conversations')
    TOTAL = int(argv[at + 1])
    del argv[at:at + 2]
if argv:
    OUT = argv[0]

SHARD_SIZE = 20
SPAN_DAYS = 3 * 365
SEED = 20260823

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None


def make_chart(width, height, bars, title):
    img = Image.new('RGB', (width, height), '#ffffff')
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width - 1, height - 1), outline='#d0d7de')
    draw.text((16, 12), title, fill='#1f2328')
    top, bottom, left = 44, height - 32, 40
    span = (width - left - 24) // max(1, len(bars))
    peak = max(bars) or 1
    for index, value in enumerate(bars):
        x0 = left + index * span + 6
        x1 = x0 + span - 14
        y0 = bottom - int((bottom - top) * value / peak)
        draw.rectangle((x0, y0, x1, bottom), fill='#4493f8')
    draw.line((left, bottom, width - 24, bottom), fill='#57606a')
    draw.line((left, top, left, bottom), fill='#57606a')
    return img


def make_diagram(width, height, boxes, title):
    img = Image.new('RGB', (width, height), '#0d1117')
    draw = ImageDraw.Draw(img)
    draw.text((16, 12), title, fill='#e6edf3')
    y = 52
    for label in boxes:
        draw.rounded_rectangle((28, y, width - 28, y + 46), radius=8,
                               fill='#161b22', outline='#30363d')
        draw.text((44, y + 18), label, fill='#e6edf3')
        if y + 96 < height:
            draw.line((width // 2, y + 46, width // 2, y + 68), fill='#4493f8', width=2)
        y += 68
    return img


def make_lines(width, height, series, title):
    img = Image.new('RGB', (width, height), '#ffffff')
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width - 1, height - 1), outline='#d0d7de')
    draw.text((16, 12), title, fill='#1f2328')
    top, bottom, left, right = 48, height - 34, 44, width - 22
    peak = max(max(line) for line in series) or 1
    colours = ['#4493f8', '#d29922', '#3fb950']
    for index, line in enumerate(series):
        points = []
        for n, value in enumerate(line):
            x = left + (right - left) * n / max(1, len(line) - 1)
            y = bottom - (bottom - top) * value / peak
            points.append((x, y))
        draw.line(points, fill=colours[index % len(colours)], width=3)
    draw.line((left, bottom, right, bottom), fill='#57606a')
    draw.line((left, top, left, bottom), fill='#57606a')
    return img


ASSETS = [
    ('file_1a2b3c4d5e6f7a8b', 'monthly-requests.png',
     lambda: make_chart(760, 380, [42, 61, 55, 78, 96, 88, 120], 'Requests per month, thousands')),
    ('file_2b3c4d5e6f7a8b9c', 'latency-before-after.png',
     lambda: make_chart(760, 380, [310, 288, 240, 96, 88, 72, 70], 'p95 latency, ms')),
    ('file_3c4d5e6f7a8b9c0d', 'pipeline.png',
     lambda: make_diagram(620, 320, ['Ingest', 'Normalize', 'Store'], 'Import pipeline')),
    ('file_4d5e6f7a8b9c0d1e', 'sourdough-crumb.png',
     lambda: make_chart(640, 340, [12, 34, 51, 47, 30, 18], 'Rise, mm per hour')),
    ('file_5e6f7a8b9c0d1e2f', 'budget-2025.png',
     lambda: make_chart(720, 360, [820, 640, 410, 380, 300, 250, 190], 'Spending by category, EUR')),
    ('file_6f7a8b9c0d1e2f3a', 'architecture.png',
     lambda: make_diagram(620, 390, ['Browser', 'Static site', 'Local files', 'No network'],
                          'Offline reading path')),
    ('file_7a8b9c0d1e2f3a4b', 'index-size-growth.png',
     lambda: make_lines(760, 360, [[4, 9, 17, 26, 38, 55, 71], [4, 6, 8, 11, 13, 15, 17]],
                        'Search index, MB: naive vs lazy')),
    ('file_8b9c0d1e2f3a4b5c', 'container-layers.png',
     lambda: make_chart(700, 350, [980, 210, 74, 32, 12], 'Image layers, MB')),
    ('file_9c0d1e2f3a4b5c6d', 'backup-topology.png',
     lambda: make_diagram(640, 390, ['Laptop', 'NAS, nightly', 'Object storage, weekly',
                                     'Cold copy, offsite'], 'Three copies, two media')),
    ('file_0d1e2f3a4b5c6d7e', 'training-loss.png',
     lambda: make_lines(740, 360, [[92, 61, 44, 33, 27, 24, 22], [92, 66, 52, 45, 43, 44, 47]],
                        'Loss: train vs validation')),
    ('file_1e2f3a4b5c6d7e8f', 'weekly-distance.png',
     lambda: make_chart(700, 340, [18, 24, 31, 27, 42, 38, 46], 'Cycling, km per week')),
    ('file_2f3a4b5c6d7e8f90', 'cache-hit-rate.png',
     lambda: make_lines(720, 340, [[41, 55, 68, 77, 84, 88, 91]], 'Cache hit rate, percent')),
]

MISSING_ASSET = 'file_9f8e7d6c5b4a3928'
BUDGET_ASSET = 'file_08a'

# Идентификатор вложения не должен зависеть от порядкового номера переписки,
# иначе файл в архиве и ссылка на него расходятся при любой перестановке
ATTACHMENT_IDS = {'budget-2025.csv': BUDGET_ASSET}


def user(text, attachments=None):
    return {'role': 'user', 'text': text, 'attachments': attachments or []}


def bot(text, tool=None):
    return {'role': 'assistant', 'text': text, 'tool': tool}


def image(pointer):
    return {'role': 'user', 'image': pointer}


# Витринные переписки. Сюда ведут ссылки с лендинга, поэтому здесь собрано всё,
# что инструмент умеет показывать: код, формулы, таблицы, картинки, шаги
# рассуждений и вызовы инструментов
SHOWCASE = [
    ('Slow PostgreSQL query on a 40M row table', [
        user('This query takes 12 seconds on a table with 40M rows:\n\n'
             '```sql\nSELECT user_id, count(*)\nFROM events\nWHERE created_at > now() - interval \'30 days\'\n'
             'GROUP BY user_id\nORDER BY count(*) DESC\nLIMIT 50;\n```\n\nWhat should I look at first?'),
        bot('Run `EXPLAIN (ANALYZE, BUFFERS)` first. With 40M rows and a 30 day window, the planner '
            'usually falls back to a sequential scan unless there is an index that covers both the '
            'filter and the grouping.\n\nA partial index tends to help here:\n\n'
            '```sql\nCREATE INDEX CONCURRENTLY events_recent_user_idx\n  ON events (user_id)\n'
            '  WHERE created_at > \'2026-01-01\';\n```\n\nThe caveat is that a hardcoded date makes the '
            'index go stale, so most teams schedule a rebuild or use a rolling partition instead.',
            'python'),
        user('Partitioning by month is on the table. Is it worth it at this size?'),
        bot('At 40M rows the win comes less from scan speed and more from maintenance: vacuum, index '
            'rebuilds and retention deletes all become per-partition operations. Dropping a partition '
            'is instant; deleting 3M rows is not.\n\nRule of thumb: partition when retention is '
            'time based, when old data is rarely queried, or when a single index no longer fits in '
            'shared buffers.'),
        image('sediment://file_2b3c4d5e6f7a8b9c'),
        bot('The drop from 310 ms to about 70 ms after the index matches what the plan predicted. '
            'The remaining time is mostly the sort, which you can avoid by pushing the limit into a '
            'lateral join if it ever becomes the bottleneck.'),
        user('One more thing: autovacuum keeps falling behind on this table.'),
        bot('Two knobs matter at this size. Lower the scale factor so vacuum triggers on a fixed '
            'fraction rather than a percentage of a huge table:\n\n'
            '```sql\nALTER TABLE events SET (\n  autovacuum_vacuum_scale_factor = 0.02,\n'
            '  autovacuum_vacuum_cost_limit = 2000\n);\n```\n\n'
            'Then check `pg_stat_progress_vacuum` during a run. If it spends most of its time in '
            '`vacuuming indexes`, the index count is the real problem, not the settings.'),
    ]),
    ('Gradient descent, but explain the math', [
        user('I keep using gradient descent without really understanding the update rule. '
             'Can you derive it?'),
        bot('Start from a loss function \\(L(\\theta)\\). The gradient \\(\\nabla L(\\theta)\\) points in '
            'the direction of steepest increase, so moving against it decreases the loss:\n\n'
            '\\[\\theta_{t+1} = \\theta_t - \\eta \\nabla L(\\theta_t)\\]\n\n'
            'The learning rate \\(\\eta\\) controls the step. For a quadratic loss '
            '\\(L(\\theta) = \\frac{1}{2}\\theta^2\\) the gradient is simply \\(\\theta\\), so the update '
            'becomes \\(\\theta_{t+1} = (1 - \\eta)\\theta_t\\). Convergence requires '
            '\\(0 < \\eta < 2\\), which is the cleanest way to see why a large learning rate diverges.'),
        user('Where does momentum fit in?'),
        bot('Momentum keeps a running average of past gradients:\n\n'
            '\\[v_{t+1} = \\beta v_t + (1 - \\beta) \\nabla L(\\theta_t)\\]\n'
            '\\[\\theta_{t+1} = \\theta_t - \\eta v_{t+1}\\]\n\n'
            'With \\(\\beta = 0.9\\) the effective step is roughly ten times the raw gradient in '
            'directions that stay consistent, while noisy directions cancel out.'),
        user('And Adam on top of that?'),
        bot('Adam adds a second moment, so each coordinate gets its own step size:\n\n'
            '\\[m_t = \\beta_1 m_{t-1} + (1-\\beta_1) g_t\\]\n'
            '\\[v_t = \\beta_2 v_{t-1} + (1-\\beta_2) g_t^2\\]\n'
            '\\[\\theta_{t+1} = \\theta_t - \\eta \\frac{\\hat{m}_t}{\\sqrt{\\hat{v}_t} + \\epsilon}\\]\n\n'
            'The hats are bias corrections, \\(\\hat{m}_t = m_t / (1 - \\beta_1^t)\\), which matter only '
            'for the first few hundred steps when both averages start at zero.'),
        image('sediment://file_0d1e2f3a4b5c6d7e'),
        bot('The gap between the two curves after step four is the usual signature of overfitting: '
            'training loss keeps falling while validation turns upward. Early stopping around the '
            'minimum of the validation curve is the cheapest fix before touching regularisation.'),
    ]),
    ('Reading a ChatGPT export without losing your mind', [
        user('I exported my data and got a 700 MB zip. conversations.json is one single line. '
             'What do people normally do with this?'),
        bot('The file is a JSON array of conversations. Each conversation has a `mapping` of nodes, '
            'and each node points at its parent, so the visible thread is the chain from '
            '`current_node` back to the root.\n\nThree things surprise everyone the first time:\n\n'
            '- edits and regenerations create branches, so the file holds more messages than the app shows\n'
            '- attachments live outside the JSON, under names that no longer carry an extension\n'
            '- exports above a certain size arrive split across `conversations-000.json` and friends'),
        image('sediment://file_6f7a8b9c0d1e2f3a'),
        bot('That is the shape worth aiming for: read the archive once, write plain HTML, and never '
            'depend on a server again. Anything that needs a running process will outlive its own '
            'usefulness the day you stop maintaining it.'),
        user('How do I walk the tree without blowing the recursion limit?'),
        bot('Iteratively, with a visited set. Some threads run deeper than Python\'s default limit '
            'of 1000 frames:\n\n'
            '```python\ndef thread(mapping, current):\n    chain, seen = [], set()\n'
            '    while current and current not in seen:\n        seen.add(current)\n'
            '        node = mapping.get(current) or {}\n        if node.get("message"):\n'
            '            chain.append(node["message"])\n        current = node.get("parent")\n'
            '    return list(reversed(chain))\n```\n\n'
            'The `seen` set is not paranoia: a handful of exports in the wild contain a node whose '
            'parent chain loops back on itself.'),
        user('And the attachments with no extension?'),
        bot('Read the first bytes and match the signature. PNG starts with `\\x89PNG\\r\\n\\x1a\\n`, '
            'JPEG with `\\xff\\xd8\\xff`, WebP is `RIFF` followed by `WEBP` at offset 8. The export '
            'also ships `conversation_asset_file_names.json`, which maps the opaque id back to the '
            'name you originally uploaded, so between the two you can restore both name and type.'),
    ]),
    ('Why is my container image 1.2 GB', [
        user('My Python service image is 1.2 GB. The code is maybe 400 KB. Where does it all go?'),
        bot('Almost always the base image plus build tooling that never gets removed. Check the '
            'layer breakdown first:\n\n```bash\ndocker history --no-trunc --format '
            '"{{.Size}}\\t{{.CreatedBy}}" myimage:latest | head -20\n```\n\n'
            'The usual suspects are `python:3.12` instead of `python:3.12-slim`, a `pip install` '
            'that keeps its cache, and build dependencies like `gcc` left in the final layer.'),
        image('sediment://file_8b9c0d1e2f3a4b5c'),
        bot('That first layer at 980 MB is the whole story. A multi-stage build moves compilation '
            'into a throwaway stage:\n\n'
            '```dockerfile\nFROM python:3.12-slim AS build\nRUN pip install --no-cache-dir '
            '--prefix=/install -r requirements.txt\n\nFROM python:3.12-slim\n'
            'COPY --from=build /install /usr/local\nCOPY . /app\n```\n\n'
            'Typical result for a service like yours is 180 to 220 MB, most of which is the '
            'interpreter itself.'),
        user('Does it matter beyond disk space?'),
        bot('Pull time on cold nodes, mostly. A 1.2 GB image on a fresh autoscaled node adds '
            'roughly 20 to 40 seconds before the container starts, which is exactly when you '
            'least want it. It also widens the CVE surface: every package in the image gets '
            'scanned and reported, including the compiler you no longer use.'),
    ]),
    ('Monthly spending review', [
        user('Here is my spending export for the year. Can you find the pattern?',
             ['budget-2025.csv']),
        bot('Grouped by category and sorted by total:\n\n'
            '| Category | EUR | Share |\n| --- | --- | --- |\n'
            '| Groceries | 820 | 31% |\n| Eating out | 640 | 24% |\n| Transport | 410 | 15% |\n'
            '| Subscriptions | 380 | 14% |\n| Everything else | 420 | 16% |\n\n'
            'The interesting line is subscriptions: 380 EUR across eleven separate charges, and '
            'four of them renewed within the same week, which is why that month looked like an '
            'anomaly.'),
        image('sediment://file_5e6f7a8b9c0d1e2f'),
        bot('Eating out tracks weeks when groceries dropped below 60 EUR, so the two are the same '
            'behaviour seen from different sides rather than two independent problems. Cutting the '
            'category directly tends to fail; planning two more meals at home usually moves both.'),
    ]),
    ('Image that never made it into the export', [
        user('I asked for a diagram in this chat and it definitely rendered at the time.'),
        bot('It did, but the file is not in the export. That happens often enough that a good '
            'reader should say so out loud instead of showing a broken image icon: the conversation '
            'references the attachment, the archive simply does not contain the bytes.'),
        image('sediment://file_9f8e7d6c5b4a3928'),
    ]),
    ('Regex for parsing nginx access logs', [
        user('I need to parse the default nginx combined log format. Every regex I write breaks on '
             'user agents with quotes in them.'),
        bot('Do not try to be clever about the quoting, anchor on the structure instead:\n\n'
            '```python\nimport re\n\nLINE = re.compile(\n    r\'^(?P<ip>\\S+) \\S+ (?P<user>\\S+) '
            r'\\[(?P<time>[^\\]]+)\\] \'\n    r\'"(?P<method>[A-Z]+) (?P<path>[^"]*?) '
            r'(?P<proto>HTTP/[\\d.]+)" \'\n    r\'(?P<status>\\d{3}) (?P<bytes>\\d+|-) \'\n'
            r'    r\'"(?P<ref>[^"]*)" "(?P<agent>.*)"$\'\n)\n```\n\n'
            'The trick is `(?P<agent>.*)$` at the end: the user agent is the last field, so anything '
            'goes until the closing quote at end of line.'),
        user('It still misses a few lines. How do I find out which?'),
        bot('Never silently drop them. Count and sample:\n\n'
            '```python\nbad = []\nfor n, line in enumerate(stream, 1):\n'
            '    if not LINE.match(line):\n        bad.append((n, line[:120]))\n'
            'print(f"unmatched: {len(bad)}")\nfor n, sample in bad[:5]:\n    print(n, sample)\n```\n\n'
            'In practice the leftovers are almost always malformed requests from scanners, where '
            'the request line is not `METHOD PATH PROTO` at all but raw junk or a TLS handshake '
            'landing on a plain HTTP port.'),
    ]),
    ('Docker compose setup for local development', [
        user('I want postgres, redis and my app in compose, but I keep losing the database on '
             'every restart.'),
        bot('The data lives in an anonymous volume unless you name it, and anonymous volumes are '
            'discarded by `docker compose down -v` and often by a plain recreate:\n\n'
            '```yaml\nservices:\n  db:\n    image: postgres:17\n    environment:\n'
            '      POSTGRES_PASSWORD: dev\n    volumes:\n      - pgdata:/var/lib/postgresql/data\n'
            '    healthcheck:\n      test: ["CMD-SHELL", "pg_isready -U postgres"]\n'
            '      interval: 5s\n\nvolumes:\n  pgdata:\n```\n\n'
            'The healthcheck matters more than it looks: without it the app starts before postgres '
            'accepts connections and you get a flaky first run every morning.'),
        image('sediment://file_3c4d5e6f7a8b9c0d'),
        bot('One more habit worth adopting: keep the compose file for infrastructure only and run '
            'the app itself on the host during development. Rebuild times drop to zero and the '
            'debugger attaches without any port gymnastics.'),
    ]),
    ('CAP theorem in plain words', [
        user('Explain CAP without the usual triangle diagram.'),
        bot('A network partition is not a choice, it is weather. The theorem is about what you do '
            'when it arrives: refuse to answer until you can be sure the answer is current, or '
            'answer from what you have and accept that it might be stale.\n\n'
            'That is the whole content. The triangle misleads because it suggests you pick two out '
            'of three at design time, when in reality you pick one of two, and only during a '
            'partition.'),
        user('So what does "AP system" mean in practice?'),
        bot('It means a read can return a value that another node has already overwritten, and the '
            'system will reconcile later. Concretely you get to decide the reconciliation rule: '
            'last write wins, vector clocks, or application-level merge. The rule is the real '
            'design decision, and it is the part that is usually left undocumented until the first '
            'incident.'),
    ]),
    ('Making sense of an old research folder', [
        user('I have 4000 files from a project I stopped in 2021. No naming convention. Where do '
             'I even start?'),
        bot('Do not open them in order. Build an inventory first, then decide:\n\n'
            '```bash\nfind . -type f -printf "%s\\t%TY-%Tm\\t%p\\n" \\\n'
            '  | sort -rn | head -50 > biggest.tsv\nfind . -type f | sed \'s/.*\\.//\' \\\n'
            '  | sort | uniq -c | sort -rn\n```\n\n'
            'Size and extension together usually reveal that 90% of the bytes are three or four '
            'kinds of artefact you can decide about in one pass, and the actual thinking lives in '
            'a few dozen small text files.'),
        user('Half of them are duplicates from different backups.'),
        bot('Hash first, compare second:\n\n'
            '```bash\nfind . -type f -size +1M -exec sha256sum {} + \\\n'
            '  | sort | uniq -w64 -D > duplicates.txt\n```\n\n'
            'Only after the list exists should you delete anything, and delete by moving to a '
            'quarantine folder you erase in a month. Every deduplication story that ends badly '
            'skipped that step.'),
    ]),
    ('Three days in Lisbon, walking distances', [
        user('Three days in Lisbon in October. I would rather walk than take transport, but I do '
             'not want 25 km days.'),
        bot('Lisbon punishes naive routing because the hills are steep and the distance on the map '
            'is not the distance in your legs. A workable split:\n\n'
            '| Day | Area | Walking | Climb |\n| --- | --- | --- | --- |\n'
            '| 1 | Baixa, Alfama, Graça | 8 km | 210 m |\n'
            '| 2 | Belém, riverside | 9 km | 40 m |\n'
            '| 3 | Príncipe Real, Bairro Alto | 7 km | 180 m |\n\n'
            'Day 2 is flat on purpose, so put it in the middle rather than at the end.'),
        user('Is the tram worth it or is it a tourist trap?'),
        bot('Both. Tram 28 is genuinely the easiest way up to Graça, and it is also packed enough '
            'that pickpocketing is a real risk in the middle of the day. Taking it uphill early, '
            'walking down, and skipping it entirely after noon gets you the useful half without '
            'the queue.'),
    ]),
    ('Sourdough starter refuses to rise', [
        user('Day 9 with my starter. Bubbles, sour smell, but it never doubles.'),
        bot('Day 9 with bubbles and a sour smell usually means the bacteria are ahead of the yeast, '
            'which is the normal way this stalls. The fix is usually feeding ratio, not time: move '
            'from 1:1:1 to 1:5:5 so the acidity drops between feeds.'),
        image('sediment://file_4d5e6f7a8b9c0d1e'),
        bot('That curve is the tell: it peaks around hour three, then collapses. Peak at three '
            'hours means you are feeding it too late, so it spends most of its day starving in its '
            'own acid. Feed at the peak, not the next morning, and the doubling shows up within '
            'two or three cycles.'),
    ]),
    ('Cache hit rate stuck at 40 percent', [
        user('My CDN cache hit rate sits at 41% and I cannot work out why.'),
        bot('Start from what is being missed rather than the aggregate. The usual causes, in the '
            'order they occur:\n\n'
            '- a `Set-Cookie` on responses that should be anonymous, which makes them uncacheable\n'
            '- `Cache-Control: private` inherited from a framework default\n'
            '- query strings used for analytics that fragment the cache key\n'
            '- `Vary: User-Agent`, which effectively gives every device its own copy'),
        user('It was the query strings. Analytics parameters on every link.'),
        bot('Then normalise the key rather than removing the parameters. Most CDNs let you ignore '
            'a list of query parameters when computing the cache key, so analytics keeps working '
            'while `?utm_source=twitter` stops creating a separate object.'),
        image('sediment://file_2f3a4b5c6d7e8f90'),
        bot('91% is roughly the ceiling for a site with any personalised surface at all. Chasing '
            'the last few points usually means caching authenticated responses, which is where '
            'cache bugs turn into data leaks.'),
    ]),
    ('Backing up 2 TB of photos properly', [
        user('I have 2 TB of photos on one external drive and that is my entire backup strategy.'),
        bot('That is not a backup, it is a second copy of a single point of failure. The rule that '
            'has survived thirty years is 3-2-1: three copies, on two kinds of media, one offsite.'),
        image('sediment://file_9c0d1e2f3a4b5c6d'),
        bot('For 2 TB the practical version is a local NAS for the nightly copy and object storage '
            'for the weekly one. At current prices the cloud leg costs roughly 10 to 12 EUR a '
            'month for that volume, which is the part people balk at and the only part that '
            'survives a fire or a theft.'),
        user('How do I know the backups actually work?'),
        bot('Restore something on a schedule. An untested backup is a belief, not a backup. Pick a '
            'random directory once a quarter, restore it to a scratch location, and compare '
            'checksums:\n\n```bash\nrestic restore latest --target /tmp/verify --include /photos/2019/07\n'
            'diff <(cd /photos/2019/07 && sha256sum * | sort) \\\n'
            '     <(cd /tmp/verify/photos/2019/07 && sha256sum * | sort)\n```'),
    ]),
    ('Why my search index got 19 MB and how to keep it fast', [
        user('Full text search over my archive means shipping a huge index to the browser. '
             'How do people keep this usable?'),
        bot('Split it in two. The list view needs titles, dates and counts, which is small and '
            'loads immediately. The full text is only needed the moment someone types, so it can '
            'be a separate file fetched on first keystroke.\n\n'
            'The difference is the whole user experience: 0.2 MB before interaction, and the '
            'remaining megabytes only for people who actually search.'),
        image('sediment://file_7a8b9c0d1e2f3a4b'),
        bot('The flat line is the lazy version. It grows too, but nobody pays for it until they '
            'use it, and by then they have already decided the archive is worth searching.'),
        user('Any trick for the search itself, or is substring matching enough?'),
        bot('For an archive this size, plain substring matching over a normalised copy is enough '
            'and has one large advantage: no index build step, no stemming surprises, no '
            'ranking to explain. The part worth spending effort on is showing the matching '
            'sentence under each hit, because that is what turns a list of titles into an answer.'),
    ]),
]

# Тематические кластеры фона. Каждая пара связана по смыслу, поэтому ответ
# всегда отвечает на свой вопрос, в какой бы переписке пара ни оказалась
CLUSTERS = {
    'postgres': [
        ('Index bloat after a bulk delete',
         'I deleted 12M rows and the index is still the same size. Why?',
         'Deleting rows marks them dead but leaves index entries until vacuum reclaims the pages, '
         'and even then the pages stay allocated to that index. `REINDEX INDEX CONCURRENTLY` is '
         'what actually returns the space.'),
        ('Connection pool sizing for a small service',
         'How many database connections should a service with 4 workers open?',
         'Start from cores, not workers. A pool of about twice the database core count is the usual '
         'ceiling, so 8 to 16 for a small instance. Beyond that throughput flattens and latency '
         'grows, because the connections queue inside postgres instead of in your pool.'),
        ('When to use JSONB instead of columns',
         'Should I store user settings as JSONB or as real columns?',
         'Columns for anything you filter or join on, JSONB for the long tail nobody queries. The '
         'moment you write a `WHERE settings->>\'plan\' = ...` that runs often, that key has earned '
         'a column and an index.'),
        ('Timezones in timestamp columns',
         'timestamptz or timestamp for event times?',
         '`timestamptz` almost always. It stores a point in time in UTC and converts on the way out; '
         '`timestamp` stores a wall clock reading with no idea which wall it was on, which becomes '
         'unrecoverable once daylight saving moves.'),
        ('Migrations that lock the table',
         'Adding a NOT NULL column locked our table for two minutes. How do people avoid that?',
         'Split it: add the column nullable, backfill in batches, add a validated check constraint, '
         'then set NOT NULL. Each step takes a brief lock instead of one long one, and the backfill '
         'can be paused if replication lag grows.'),
        ('Counting rows without the full scan',
         'Is there a fast approximate count for a huge table?',
         'For monitoring, read `reltuples` from `pg_class`, which the planner keeps roughly current. '
         'It is off by a few percent between vacuums, which is fine for a dashboard and wrong for '
         'invoicing.'),
        ('Why my index is not being used',
         'The index exists but EXPLAIN shows a sequential scan.',
         'Usually one of three things: the query returns a large fraction of the table so the scan '
         'really is cheaper, the types do not match so the index is not applicable, or statistics '
         'are stale. `ANALYZE` the table first, then compare with `SET enable_seqscan = off` to see '
         'what the planner thinks the index would cost.'),
        ('Read replicas and stale reads',
         'Users see their own edits disappear after saving. Replica lag?',
         'Almost certainly. Route reads that follow a write by the same user to the primary for a '
         'short window, or track the write LSN in the session and wait for the replica to reach it. '
         'The general fix is read-your-writes consistency, not lower lag.'),
    ],
    'python': [
        ('Why my list comprehension is slower than a loop',
         'A comprehension building 2M items is slower than the equivalent loop. Expected?',
         'Not usually, so look at what is inside. A comprehension that calls a method per item pays '
         'the attribute lookup every time; hoisting it out (`append = out.append`) or using a '
         'generator when you do not need the list is what actually moves the number.'),
        ('Reading a huge JSON file without loading it',
         'A 300 MB JSON array does not fit comfortably in memory. Options?',
         'Stream it. Either a pull parser like `ijson`, or, if the structure is a flat array of '
         'objects, read in chunks and use `json.JSONDecoder().raw_decode` to peel one object at a '
         'time. Memory then depends on the largest single object, not on the file.'),
        ('Dataclasses versus plain dicts',
         'Is there a real reason to use dataclasses over dicts for internal data?',
         'Typos become errors instead of silent `None`, and the field list is documentation that '
         'cannot drift. The cost is a small allocation overhead, which matters only in the hottest '
         'loops. With `slots=True` even that mostly disappears.'),
        ('Virtual environments and system packages',
         'Should the venv see system site-packages?',
         'No, except when you deliberately depend on a system build of something heavy like GTK '
         'bindings. Inheriting site-packages is the most common source of "works on my machine", '
         'because the environment is no longer described by requirements alone.'),
        ('Catching exceptions without hiding bugs',
         'How specific should except clauses be?',
         'Specific enough that an unexpected failure still crashes. `except Exception` around an '
         'entire request handler is fine if it logs and re-raises in development; the same clause '
         'around three lines of parsing will swallow the typo that broke them.'),
        ('Type hints on a codebase that has none',
         'Where do you start adding type hints to an existing project?',
         'At the boundaries: function signatures on public modules first, internals never. Run the '
         'checker in non-blocking mode for a few weeks so the noise is visible without stopping '
         'anyone, then turn on strictness one module at a time.'),
        ('Subprocess without the shell',
         'Is shell=True ever acceptable?',
         'When the command genuinely is a shell pipeline you control end to end, and never with any '
         'value that came from outside the program. The list form avoids quoting entirely, which is '
         'both safer and easier to read.'),
        ('Making a script importable and runnable',
         'How do I structure a file that is both a module and a CLI?',
         'Keep the work in functions, put argument parsing in `main()`, and guard with '
         '`if __name__ == "__main__": sys.exit(main())`. Return codes from `main` then work for both '
         'the shell and the tests.'),
    ],
    'git': [
        ('Undoing a commit that is already pushed',
         'I pushed a bad commit to a shared branch. Reset or revert?',
         'Revert. It creates a new commit that undoes the change and leaves everyone else\'s history '
         'intact. Reset plus force push rewrites what others have already pulled, which turns your '
         'small mistake into everyone\'s afternoon.'),
        ('Rebase versus merge for a small team',
         'Does rebasing actually help with two people?',
         'Marginally. The real value of rebase is a readable history when many branches land per '
         'day. With two people the cost of the occasional botched rebase usually exceeds the '
         'benefit, so merge and squash on the way in is a calmer default.'),
        ('Finding when a bug appeared',
         'The bug exists now and did not three months ago. Faster way than reading diffs?',
         '`git bisect run` with a script that exits non-zero on failure. Twelve builds cover three '
         'months of daily commits, and the script means you can walk away while it works.'),
        ('Committing large files by accident',
         'A 400 MB file is in the history. Removing it from HEAD did not shrink the repo.',
         'It cannot: the object still lives in history. `git filter-repo --strip-blobs-bigger-than '
         '10M` rewrites it out, after which everyone must reclone. Add the pattern to `.gitignore` '
         'in the same change, otherwise it comes back in a week.'),
        ('Keeping secrets out of a repository',
         'What is the practical way to stop credentials landing in commits?',
         'Two layers: a pre-commit hook that scans staged content, and push protection on the '
         'hosting side as a backstop. Neither is sufficient alone, because hooks are skipped with '
         '`--no-verify` and server-side scanning only sees what already left your machine.'),
        ('Cherry-pick without dragging half the branch',
         'I need one commit from a long branch, not the rest.',
         '`git cherry-pick <sha>` is the direct answer, but check whether the commit depends on '
         'earlier ones first. If it does, the conflict you get is real information: the change was '
         'never independent, and copying it alone will compile but misbehave.'),
        ('Signed commits, worth it or theatre',
         'Does commit signing matter for a solo public project?',
         'It proves commits came from a key you control, which matters mostly for released tags and '
         'for actions others automate against. For everyday commits on a one-person project it is '
         'largely ceremony, and an expired key causes more confusion than it prevents.'),
    ],
    'frontend': [
        ('Dropping a CSS framework from a small site',
         'Is removing Bootstrap from a five page site worth the effort?',
         'Usually yes at that size. Grid and flexbox cover the layout, custom properties cover the '
         'theming, and you stop shipping 200 KB to style five pages. The part people underestimate '
         'is the component behaviour, not the styles: modals and dropdowns have to be rewritten.'),
        ('Dark mode without a flash of white',
         'Switching to dark theme flashes white on load. How do people avoid it?',
         'Set the theme before first paint with a tiny inline script in the head that reads the '
         'stored preference and puts an attribute on the root element. Anything loaded as an '
         'external file arrives too late, which is exactly what the flash is showing you.'),
        ('When a static site stops being enough',
         'At what point does a static site need a backend?',
         'When you need to keep a secret or write shared state. Everything else, including search '
         'over your own content, can be done in the browser with a prebuilt index, and it stays '
         'working long after any server you would have written stops being maintained.'),
        ('Fonts that do not shift the layout',
         'Web font swaps cause a visible reflow. Fix?',
         '`font-display: swap` plus a fallback stack with matched metrics. The modern lever is '
         '`size-adjust` and `ascent-override` on the fallback `@font-face`, which lets the '
         'substitute occupy the same space, so the swap becomes invisible rather than merely fast.'),
        ('Images that do not push content around',
         'Why does my page jump while images load?',
         'Because the browser does not know their size until the bytes arrive. Set `width` and '
         '`height` attributes, or an `aspect-ratio` in CSS, and the space is reserved from the '
         'first layout pass.'),
        ('Making a table readable on a phone',
         'A six column table is unusable on mobile. Options?',
         'Either let it scroll horizontally inside a container with a visible edge fade, or '
         'restructure into cards below a breakpoint. Hiding columns is the tempting third option '
         'and the one people regret, because the hidden column is always the one someone needed.'),
        ('Prefetching without wasting data',
         'Is prefetching links worth it on a content site?',
         'On hover, yes, and it is nearly free: by the time the click lands the document is often '
         'already there. Prefetching everything visible is the version that burns other people\'s '
         'data plan for a marginal gain.'),
    ],
    'linux': [
        ('Finding what fills the disk',
         'df says 96% full, du disagrees. What is going on?',
         'Almost always a deleted file still held open by a process, so the space is gone but no '
         'path points at it. `lsof +L1` lists them; restarting the holder releases the space '
         'instantly.'),
        ('Systemd service that restarts too eagerly',
         'My service restarts in a loop and floods the journal.',
         'Add a backoff. `RestartSec=5` plus `StartLimitIntervalSec=120` and `StartLimitBurst=5` '
         'turns a hot loop into five attempts and then a stop, which is what you want: a service '
         'that cannot start should stay down loudly rather than churn quietly.'),
        ('Reading logs without drowning',
         'journalctl output is overwhelming during an incident.',
         'Narrow before you read: `journalctl -u myservice --since "10 min ago" -p warning` gives '
         'the unit, the window and the severity in one line. `-o cat` strips the metadata once you '
         'know where you are.'),
        ('Permissions for a shared directory',
         'Two users need to write to the same folder without stepping on each other.',
         'A shared group plus the setgid bit: `chgrp team dir && chmod 2775 dir`. New files inherit '
         'the group, which is the part plain `chmod 775` misses and the reason it stops working on '
         'the second day.'),
        ('Cron jobs that work by hand but not on schedule',
         'The script runs fine in my shell and does nothing from cron.',
         'Cron runs with a minimal environment and no profile. Use absolute paths, set `PATH` at the '
         'top of the crontab, and redirect output to a file so the failure has somewhere to appear. '
         'Nine times in ten the missing piece is one of those three.'),
        ('Copying millions of small files',
         'rsync of a directory with 2M small files takes forever.',
         'The bottleneck is per-file syscalls, not bandwidth. `tar` piped over ssh moves them as a '
         'single stream and is often several times faster; rsync becomes the right tool again on '
         'the second run, when only the differences matter.'),
    ],
    'security': [
        ('Storing API keys in a desktop app',
         'Where should a local app keep an API key?',
         'In the OS keychain, through the platform API rather than a file you encrypt yourself. Any '
         'scheme where the app can decrypt the key without user interaction is obfuscation, so the '
         'honest choice is the keychain, and telling the user plainly that anything on their disk '
         'is readable by anything running as them.'),
        ('Hashing passwords in 2026',
         'bcrypt, scrypt or argon2 for a new project?',
         'Argon2id with the current OWASP parameters, and bcrypt only when a library constraint '
         'forces it. What matters more than the choice is that the cost parameter is revisited: a '
         'setting tuned five years ago is now cheap to attack.'),
        ('Rate limiting a public endpoint',
         'What is a sane rate limit design for a public API?',
         'Token bucket per key and per IP, with the limit expressed in the response headers so '
         'clients can behave. The subtle part is what you do on limit: a 429 with `Retry-After` is '
         'cooperative, silently dropping is what turns one misbehaving client into a retry storm.'),
        ('CSRF when the API is token based',
         'Do I need CSRF protection if I use bearer tokens?',
         'Not if the token lives in memory and is sent in a header, because the browser will not '
         'attach it automatically. The moment it moves into a cookie for convenience, CSRF is back, '
         'and `SameSite=Lax` becomes load-bearing.'),
        ('Dependency updates without breaking everything',
         'How often should a small project bump dependencies?',
         'Monthly for a project with a test suite, immediately for anything with a published '
         'advisory. Batch the routine bumps into a single change so the diff is reviewable, and '
         'keep security updates separate so they can go out without waiting for a release.'),
    ],
    'ml': [
        ('Choosing a train test split for tiny data',
         'With 800 labelled examples, is an 80/20 split reasonable?',
         'Use cross validation instead. At 800 examples a single 20% test set is 160 rows, and the '
         'variance between splits will exceed the differences you are trying to measure. Five fold '
         'gives you a mean and a spread, and the spread is the honest part.'),
        ('Class imbalance that resists resampling',
         'One class is 3% of the data and oversampling barely helps.',
         'Change the metric before changing the data. Accuracy is meaningless here; precision-recall '
         'AUC and a threshold chosen from the business cost of each error type usually reveal that '
         'the model was fine and the decision rule was wrong.'),
        ('Embeddings for search on a small corpus',
         'Are embeddings worth it for searching 5000 documents?',
         'Often not. Lexical search handles exact terms, names and identifiers, which is most of '
         'what people type. Embeddings pay off for paraphrase-heavy queries, and the honest setup is '
         'hybrid, with lexical results ranked first when the query looks like an identifier.'),
        ('Why validation loss goes up while training loss falls',
         'Classic overfitting or something else?',
         'Classic overfitting if the curves separate smoothly. If validation loss jumps around, '
         'suspect the split instead: leakage between sets, or a validation set too small to be '
         'stable. Plot both losses per epoch before touching regularisation.'),
        ('Reproducibility across machines',
         'Same code, same data, different results on another machine.',
         'Seed every source of randomness, pin the library versions, and disable nondeterministic '
         'kernels on the GPU. Even then expect small differences from floating point order; the goal '
         'is results that agree within noise, not bitwise equality.'),
    ],
    'writing': [
        ('Making documentation people actually read',
         'Our README is thorough and nobody reads it. Why?',
         'Because it answers questions in the author\'s order, not the reader\'s. Lead with what the '
         'thing does in one sentence, then how to run it, then the caveats. Anything a reader cannot '
         'act on in the first screen is reference material and belongs further down.'),
        ('Writing a changelog worth keeping',
         'What belongs in a changelog entry?',
         'What changed for the user and what they have to do about it. Internal refactors do not '
         'belong unless they change behaviour, and "various bug fixes" is a line that costs '
         'attention while carrying nothing.'),
        ('Cutting a text in half without losing content',
         'How do you shorten a document that feels bloated?',
         'Delete every sentence that restates the previous one, then every adjective that would '
         'survive being wrong. What remains is usually 60% of the length and all of the meaning. If '
         'a paragraph resists, it is doing two jobs and wants splitting rather than trimming.'),
        ('Commit messages that help later',
         'What makes a commit message useful six months on?',
         'The why. The diff already shows what changed; what it cannot show is the constraint that '
         'made the change necessary, the option you rejected, or the bug number that explains it.'),
    ],
    'career': [
        ('Comparing two offers with different equity',
         'One offer has more cash, the other more equity. How do I compare them?',
         'Value the equity at zero and see whether the decision changes. If the lower-cash offer '
         'still wins on work and people, the equity is upside. If it only wins with the equity '
         'counted at face value, you are being paid in a lottery ticket priced by the seller.'),
        ('Leaving a job without burning it down',
         'How much notice is reasonable when the handover is complex?',
         'Whatever the contract says, plus a written handover that outlives you: runbooks, access '
         'list, the three things that break at 3am. Extending the notice period rarely helps; '
         'writing things down always does.'),
        ('Interviewing when you hate whiteboards',
         'Any way to opt out of whiteboard interviews without seeming difficult?',
         'Offer a substitute rather than a refusal: a take-home you have already done, a walkthrough '
         'of public work, or pair debugging on their codebase. Companies that decline all three have '
         'told you something useful about how they work.'),
        ('Estimating work you have never done',
         'How do you estimate a task with unknown parts?',
         'Timebox the unknown separately. Estimate the known work normally, then add an explicit '
         'investigation slot with a decision point at the end. Merging the two produces a number '
         'that is wrong in a way nobody can inspect.'),
    ],
    'home': [
        ('Quiet mini PC for a bedroom',
         'Which mini PC is quiet enough to sit in a bedroom?',
         'Anything fanless with a passive case, or a laptop-class chip undervolted and capped below '
         'its turbo. The noise people actually notice is not the fan at load but the pulsing at '
         'idle, so a fan curve with a wide hysteresis matters more than the rated decibels.'),
        ('Fixing a wobbly standing desk',
         'My desk wobbles at full height. Anything short of replacing it?',
         'A cross brace at the back removes most of the sway, and moving the heaviest item to the '
         'centre helps more than it should. If the wobble is front to back rather than side to side, '
         'the feet are the problem and shims fix it in five minutes.'),
        ('Cold brew that is not bitter',
         'What ratio and time for cold brew that does not taste harsh?',
         '1:8 coffee to water by weight for a concentrate, 16 to 18 hours in the fridge, coarse '
         'grind. Harshness at that ratio is usually grind size rather than time: too fine and you '
         'over-extract even cold.'),
        ('Meal plan that survives a busy week',
         'How do I plan dinners that still happen on the bad days?',
         'Plan four, not seven, and make one of them deliberately trivial. The plans that fail are '
         'the ones with no slack, because a single late evening cascades into ordering food for the '
         'rest of the week.'),
        ('Bike gears that skip under load',
         'The rear derailleur skips on the third gear when I push hard.',
         'Cable tension first: a quarter turn on the barrel adjuster while pedalling usually finds '
         'it. If it only skips under load and shifts cleanly otherwise, suspect a worn cassette '
         'paired with a new chain, which no amount of adjustment fixes.'),
    ],
    'archives': [
        ('Keeping a personal archive readable in ten years',
         'What format survives a decade of neglect?',
         'Plain text and HTML with no build step, images in formats older than the archive itself. '
         'The test is not whether it opens today but whether it opens with no software you have to '
         'install first.'),
        ('Deciding what not to keep',
         'How do you decide what is worth archiving at all?',
         'Keep what you cannot recreate and what you would miss. Everything downloadable again is a '
         'cache, not an archive, and treating the two the same is what turns 200 GB of real memories '
         'into 4 TB of noise.'),
        ('Checksums for a photo library',
         'Is bit rot a real concern for a home library?',
         'Real but slow. A yearly checksum pass over a few terabytes catches it long before you '
         'notice visually, and the value is knowing which copy is the good one when two disagree. '
         'Without checksums, sync happily propagates the corrupted file over the intact one.'),
        ('Exporting everything from a service before leaving',
         'What do I collect before deleting an account?',
         'The official export, a screenshot of the settings, and a note about what the export did '
         'not include. That last one is the part nobody writes down, and it is what you need when '
         'you open the archive years later and wonder what is missing.'),
    ],
    'observability': [
        ('Logs, metrics or traces first',
         'Small service, limited time. Which one first?',
         'Logs with structure, because they answer "what happened" for incidents you did not '
         'anticipate. Metrics come next for the handful of numbers you would page on. Traces are '
         'worth it once a request crosses more than two services.'),
        ('Alerts nobody ignores',
         'Our alerts fire constantly and everyone mutes them.',
         'Alert on symptoms users feel, not on causes. Disk at 85% is a cause and often harmless; '
         'requests failing is a symptom and always matters. Every alert that cannot be acted on '
         'immediately should be a dashboard instead.'),
        ('Cardinality that kills the metrics bill',
         'Our metrics cost exploded after adding a user id label.',
         'That is the mechanism: every distinct label value creates a series. User ids, request ids '
         'and full URLs never belong in labels. Put them in logs and traces, where high cardinality '
         'is the point rather than the problem.'),
        ('Sampling traces without losing the bad ones',
         'Head sampling drops exactly the requests I want to see.',
         'Tail sampling: buffer the spans and decide after the outcome is known, keeping everything '
         'that errored or exceeded a latency threshold plus a small random slice of the rest. Costs '
         'more memory at the collector and is almost always worth it.'),
    ],
    'testing': [
        ('Tests that fail only in CI',
         'Everything passes locally and CI fails at random.',
         'Three usual causes: leftover state between tests that a fresh CI container does not have, '
         'timing assumptions that a slower machine breaks, and a shared resource like a fixed port '
         'or a real clock. Run the suite locally in a random order to reproduce the first one.'),
        ('How much coverage is enough',
         'Is 80% coverage a reasonable target?',
         'Coverage measures what ran, not what was checked. A suite at 80% with meaningful '
         'assertions is healthy; the same number reached by importing modules is decoration. Track '
         'it as a trend and never as a gate.'),
        ('Testing code that talks to the network',
         'Mock the HTTP client or spin up a fake server?',
         'A fake server, when the protocol matters. Mocks encode your belief about the API, so they '
         'keep passing after the real one changes. A local server exercises serialisation, headers '
         'and timeouts, which is where the bugs actually live.'),
        ('Edge cases worth writing down',
         'Which edge cases deserve a test in a small project?',
         'The ones that already bit you, and the boundaries: empty, one, many, malformed, and the '
         'largest input you claim to support. That list catches most regressions without turning '
         'the suite into a second implementation.'),
    ],
    'photography': [
        ('Culling thousands of photos quickly',
         'I come back from a trip with 2000 photos and never sort them.',
         'Two passes, both fast. First pass rejects only: anything out of focus or duplicated, no '
         'thinking. Second pass picks the keepers from what survived. Trying to judge quality on the '
         'first pass is what makes people abandon the whole thing.'),
        ('RAW or JPEG for casual shooting',
         'Is RAW worth the storage for holiday photos?',
         'For photos you will edit, yes; for the rest it is a tax you pay forever. A practical '
         'middle ground is RAW plus JPEG on trips and JPEG only for everyday shots, then discarding '
         'the RAWs you never opened after a year.'),
        ('Colour that looks different on every screen',
         'My edits look wrong on the phone.',
         'Untagged exports assume sRGB and phones do not. Export with the profile embedded and edit '
         'on a display you have calibrated at least once. Perfect agreement is not achievable, '
         'consistent-enough is.'),
    ],
    'music': [
        ('Learning an instrument as an adult',
         'Is it realistic to start piano at 35?',
         'Yes, with the caveat that adults quit for reasons children do not: impatience with the '
         'first plateau, and practice sessions scheduled at the end of the day when willpower is '
         'gone. Twenty minutes in the morning beats an hour promised for the evening.'),
        ('Practising without annoying neighbours',
         'How do people practise in a flat?',
         'A digital instrument with headphones for volume, and a rug plus felt pads for the '
         'structure-borne noise that headphones do not solve. The complaints are usually about '
         'thumping through the floor rather than the sound in the air.'),
    ],
    'language': [
        ('First week with a new spoken language',
         'How should I structure week one of learning a language?',
         'Sound before grammar. Spend the first week on pronunciation and the hundred most frequent '
         'words, because everything later is easier once your ear can segment speech. Grammar drills '
         'in week one produce people who can conjugate and cannot hear.'),
        ('Vocabulary that sticks',
         'Flashcards work for a while then stop. Why?',
         'Isolated words decay because nothing retrieves them. Cards with a sentence you actually '
         'encountered survive, because the context provides the hook. The rule of thumb is to add '
         'nothing you have not met in the wild.'),
        ('Explaining recursion to a beginner',
         'How do I explain recursion without factorials?',
         'Use a task that is obviously self-similar in the physical world: looking for a key in '
         'nested boxes. Open a box; if it holds a key you are done, if it holds boxes you repeat the '
         'same instruction on each. The base case becomes obvious because an empty box is obvious.'),
    ],
    'unicode': [
        ('Strings that look identical but compare unequal',
         'Two visually identical strings fail an equality check.',
         'Almost certainly composed versus decomposed forms: "é" as one code point or as "e" plus a '
         'combining accent. Normalise both sides with NFC before comparing, and store normalised so '
         'the problem does not come back through a different door.'),
        ('Sorting names in several languages',
         'Alphabetical sort puts accented names at the end.',
         'Byte order is not alphabetical order. Use a locale-aware collator, and pick the locale '
         'deliberately, because Swedish and German disagree about where "ä" belongs and both are '
         'right for their readers.'),
        ('Counting characters that users recognise',
         'len() disagrees with what users see as one character.',
         'Because a user-perceived character can be several code points: an emoji with a skin tone '
         'modifier is one grapheme and up to four code points. Count grapheme clusters when the '
         'number is shown to a person, code points when it is a storage limit.'),
    ],
    'meetings': [
        ('Cutting a team from twelve meetings a week',
         'Twelve recurring meetings and nobody remembers why half exist.',
         'Cancel them all for two weeks and let people re-request what they miss. Roughly a third '
         'never come back, a third return shorter, and the remainder turn out to be the ones doing '
         'real work. Trimming them one at a time never produces that clarity.'),
        ('Making a status meeting unnecessary',
         'Can a status meeting be replaced by writing?',
         'Usually, if the writing is prompt and someone reads it. The failure mode is a written '
         'update nobody responds to, which is worse than the meeting because it has all of the cost '
         'and none of the acknowledgement.'),
    ],
    'stats': [
        ('What a p-value actually tells you',
         'I keep hearing p-values are misused. What do they mean?',
         'The probability of data at least this extreme if the null hypothesis were true. That is '
         'all. It is not the probability the hypothesis is false, and a small p with a tiny effect '
         'size usually means a large sample rather than an important finding.'),
        ('Sample size before running the test',
         'How many users do I need for an A/B test?',
         'It depends on the effect you would act on, not the effect you hope for. Decide the '
         'smallest difference worth shipping, then compute the size for that. Running until '
         'significance appears is the most common way to get a result that will not replicate.'),
        ('Choosing a chart for a five point scale',
         'Bar chart or stacked bar for survey responses?',
         'Diverging stacked bars centred between agree and disagree, because the question people ask '
         'is which way opinion leans. Plain stacked bars force the reader to compare segment lengths '
         'that do not share a baseline.'),
    ],
    'api': [
        ('Versioning an API without pain later',
         'Path versioning or headers?',
         'Path versioning, for a small team. It is visible in logs, cacheable, and trivially '
         'explained. Header negotiation is more elegant and is the version people get wrong in '
         'curl, in caches and in the one client that matters.'),
        ('Pagination that survives inserts',
         'Offset pagination skips rows when new ones arrive.',
         'Use a keyset: order by a stable column plus the primary key, and pass the last seen values '
         'as the cursor. Offsets are computed against a moving table, which is precisely why rows '
         'appear twice or vanish.'),
        ('Errors clients can act on',
         'What should an API error body contain?',
         'A stable machine-readable code, a human sentence, and, when the fault is the client\'s, '
         'which field. Stack traces help nobody outside your team, and a bare 400 turns every '
         'integration into guesswork.'),
    ],
}

# Пары, ради которых стоит открывать случайную переписку: код, формулы и таблицы
# в фоне, а не только в витрине
EXTRA_CLUSTERS = {
    'sqlite': [
        ('Full text search in SQLite without a server',
         'Can SQLite do decent full text search on a few hundred thousand rows?',
         'Yes, FTS5 handles that size comfortably:\n\n'
         '```sql\nCREATE VIRTUAL TABLE notes_fts USING fts5(title, body, content=notes);\n'
         'INSERT INTO notes_fts(notes_fts) VALUES(\'rebuild\');\n'
         'SELECT title, snippet(notes_fts, 1, \'<b>\', \'</b>\', \'...\', 12)\n'
         'FROM notes_fts WHERE notes_fts MATCH \'archive NEAR/5 export\';\n```\n\n'
         'The `snippet` function is the part people miss: it returns the matching fragment, which '
         'is what makes results readable rather than a list of titles.'),
        ('WAL mode and concurrent readers',
         'Do I need WAL mode for a read-heavy SQLite database?',
         'Almost always. In the default journal mode a writer blocks readers; in WAL they proceed '
         'in parallel:\n\n```sql\nPRAGMA journal_mode = WAL;\nPRAGMA synchronous = NORMAL;\n```\n\n'
         'The tradeoff is that WAL needs shared memory, so it does not work over most network '
         'filesystems. On a local disk it is strictly better for this workload.'),
        ('Storing timestamps in SQLite',
         'SQLite has no date type. What do people store?',
         'Integer Unix seconds for anything you compare or sort, and ISO-8601 text only when humans '
         'read the file directly. Mixing the two in one column is the failure mode, because '
         'comparisons then silently sort text against numbers.'),
        ('Vacuuming a database that only grows',
         'My SQLite file never shrinks after deletes.',
         'Freed pages are reused, not returned, unless you ask:\n\n'
         '```sql\nPRAGMA auto_vacuum = INCREMENTAL;   -- set before the first table is created\n'
         'PRAGMA incremental_vacuum(1000);\n```\n\n'
         'On an existing database only a full `VACUUM` reclaims space, and it needs room for a '
         'second copy of the file while it runs.'),
    ],
    'bash': [
        ('Safe defaults for a shell script',
         'What should be at the top of every bash script?',
         'Three lines that turn silent breakage into loud breakage:\n\n'
         '```bash\n#!/usr/bin/env bash\nset -euo pipefail\nIFS=$\'\\n\\t\'\n```\n\n'
         '`-e` stops on error, `-u` rejects unset variables, `pipefail` makes a failing command '
         'inside a pipe fail the whole pipe. The last one is what catches `curl ... | tar x` '
         'quietly producing nothing.'),
        ('Looping over filenames with spaces',
         'My loop breaks on filenames containing spaces.',
         'Word splitting is doing exactly what it was told. Use null separators end to end:\n\n'
         '```bash\nfind . -name \'*.json\' -print0 |\n  while IFS= read -r -d \'\' file; do\n'
         '    printf \'%s\\n\' "$file"\n  done\n```\n\n'
         'The quotes around `"$file"` matter as much as the null delimiter; either one alone still '
         'breaks.'),
        ('Retrying a flaky command',
         'How do I retry a network command a few times in bash?',
         'A small loop with backoff beats reaching for a tool:\n\n'
         '```bash\nfor attempt in 1 2 3 4 5; do\n  if curl -fsS "$url" -o "$out"; then break; fi\n'
         '  sleep $(( attempt * 2 ))\ndone\n```\n\n'
         'The `-f` is essential: without it curl exits zero on a 500 and writes the error page into '
         'your output file.'),
        ('Comparing two directories quickly',
         'What is the fastest way to check whether two directories match?',
         'Checksums of the file list, not a byte-by-byte diff:\n\n'
         '```bash\ncd a && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/a.txt\n'
         'cd ../b && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/b.txt\n'
         'diff /tmp/a.txt /tmp/b.txt\n```\n\n'
         'This also tells you which side differs, which `diff -r` on large trees takes far longer '
         'to reach.'),
    ],
    'perf': [
        ('Measuring before optimising',
         'Where do I start when a script is slow and I have no idea why?',
         'Profile before guessing. For Python:\n\n'
         '```bash\npython -m cProfile -s cumtime script.py 2>&1 | head -25\n```\n\n'
         'Read the cumulative column first, not the per-call one. Nine times out of ten the top '
         'entry is a function nobody suspected, and the one you were about to optimise is at 2%.'),
        ('Big O that matters and Big O that does not',
         'Is an O(n log n) algorithm always better than O(n squared) here?',
         'Only past the crossover point. With constants \\(c_1\\) and \\(c_2\\), the comparison is '
         '\\(c_1 n \\log n\\) against \\(c_2 n^2\\), so the quadratic version wins while '
         '\\(n < c_1 \\log n / c_2\\). For small n with a cache-friendly layout that boundary is '
         'often in the thousands, which is why insertion sort survives inside real sort '
         'implementations.'),
        ('Latency numbers worth memorising',
         'Rough numbers for what is fast and what is not?',
         'The orders of magnitude, not the digits:\n\n'
         '| Operation | Time |\n| --- | --- |\n| L1 cache reference | 1 ns |\n'
         '| Main memory reference | 100 ns |\n| SSD random read | 100 us |\n'
         '| Round trip in a datacenter | 500 us |\n| Round trip across an ocean | 150 ms |\n\n'
         'The useful consequence: one network call costs as much as a million memory accesses, so '
         'batching calls beats optimising the code between them.'),
        ('When caching makes things slower',
         'We added a cache and p99 got worse.',
         'Classic signature of a cache that misses under load: every miss now pays the lookup plus '
         'the original work, and the population step often serialises on a lock. Measure hit rate '
         'before and after, and add jitter to expiry so entries do not all die in the same second.'),
    ],
    'probability': [
        ('Bayes rule on a medical test',
         'A test is 99% accurate and I tested positive. Am I 99% likely to be ill?',
         'No, and the gap is the whole point of the rule:\n\n'
         '\\[P(D \\mid +) = \\frac{P(+ \\mid D)\\,P(D)}{P(+ \\mid D)P(D) + P(+ \\mid \\lnot D)P(\\lnot D)}\\]\n\n'
         'With a prevalence \\(P(D) = 0.001\\) and both error rates at 1%, this gives roughly '
         '\\(0.09\\). Nine percent, not ninety-nine, because false positives are drawn from a pool '
         'a thousand times larger.'),
        ('Expected value of a repeated bet',
         'Positive expected value means I should take the bet every time?',
         'Only if you can survive the variance. Repeated multiplicative bets are governed by the '
         'geometric mean, not the arithmetic one:\n\n'
         '\\[g = \\prod_i (1 + r_i)^{p_i}\\]\n\n'
         'A bet with positive arithmetic expectation can still have \\(g < 1\\), which means '
         'certain ruin over enough repetitions. That is the whole content of the Kelly criterion.'),
        ('Birthday collisions in identifiers',
         'How long should a random id be to avoid collisions?',
         'Use the birthday approximation: collisions become likely around \\(\\sqrt{N}\\) draws from '
         'a space of size \\(N\\). For a 64-bit id that is about 4 billion items, for 128 bits it '
         'is beyond anything you will generate. The practical answer for most systems is 128 random '
         'bits and no coordination.'),
    ],
    'datamodel': [
        ('Soft deletes that do not haunt you',
         'Is a deleted_at column a good idea?',
         'It is, provided every query filters on it, which is the part that fails. A partial index '
         'plus a view is the version that survives:\n\n'
         '```sql\nCREATE VIEW active_users AS SELECT * FROM users WHERE deleted_at IS NULL;\n'
         'CREATE INDEX users_active_idx ON users (id) WHERE deleted_at IS NULL;\n```\n\n'
         'Then application code selects from the view and forgetting the filter becomes impossible '
         'rather than merely discouraged.'),
        ('Natural keys versus surrogate keys',
         'Should the primary key be the email or a generated id?',
         'A surrogate id, with a unique constraint on the email. Natural keys change: people change '
         'emails, countries change codes, ISBNs get reissued. Every one of those becomes a '
         'cascading update across every table that referenced it.'),
        ('Modelling money without rounding errors',
         'Float or integer for prices?',
         'Integer minor units, or a decimal type where the database has one. Floats cannot '
         'represent 0.10 exactly, so sums drift by cents and the drift shows up in reconciliation '
         'months later. Store 1099, format as 10.99 at the edge.'),
        ('Storing enum-like values',
         'Database enum, lookup table or plain text?',
         'A lookup table with a foreign key, unless the set is genuinely fixed forever. Database '
         'enums require a migration to add a value and cannot carry attributes; plain text accepts '
         'typos silently and then you have three spellings of the same status in production.'),
    ],
    'concurrency': [
        ('Why my threads do not speed anything up',
         'Four threads and the CPU-bound job takes the same time.',
         'The interpreter lock serialises bytecode execution, so threads help with waiting, not '
         'with computing. Processes are the fix for CPU-bound work:\n\n'
         '```python\nfrom concurrent.futures import ProcessPoolExecutor\n\n'
         'with ProcessPoolExecutor() as pool:\n    results = list(pool.map(work, items, chunksize=64))\n```\n\n'
         '`chunksize` matters more than the worker count: without it, small tasks spend all their '
         'time being serialised between processes.'),
        ('Deadlock that only happens under load',
         'Two transactions deadlock occasionally in production.',
         'They take the same locks in different orders, and only concurrency makes that visible. '
         'Establish a global ordering, usually by sorting the ids you touch before touching them. '
         'Retry logic is a bandage: correct, necessary, and not a substitute for the ordering.'),
        ('Async that is somehow slower',
         'Rewriting to async made throughput worse.',
         'Something synchronous is running inside the event loop, usually a blocking library call '
         'or CPU work. One blocking call stalls every other task on that loop. Run those in a '
         'thread executor, and measure with a loop-lag metric so the next one is visible '
         'immediately.'),
    ],
    'selfhosting': [
        ('Reverse proxy with automatic certificates',
         'Simplest way to get HTTPS in front of a few home services?',
         'Caddy, because certificate handling is the default rather than a plugin:\n\n'
         '```caddy\narchive.example.com {\n    reverse_proxy 127.0.0.1:8080\n    encode zstd gzip\n}\n```\n\n'
         'That is the entire configuration, certificates included. The equivalent nginx setup is '
         'four times longer and needs a separate renewal timer that fails silently.'),
        ('Exposing a home service safely',
         'Is port forwarding to a home server a bad idea?',
         'It is a decision, not a mistake, but the safe version has three parts: no admin '
         'interfaces exposed, automatic updates on whatever is exposed, and a separate VLAN so a '
         'compromise does not reach the rest of the house. A VPN or a tunnel avoids all three '
         'questions, at the cost of client setup.'),
        ('Backups for a self-hosted setup',
         'What is the minimum backup for a home server?',
         'The data volumes and the compose files, nothing else. Containers are rebuildable; the '
         'database and the uploads are not. A nightly `restic` snapshot to a second machine plus a '
         'weekly copy offsite covers the realistic failure modes: disk death, deletion, and theft.'),
    ],
    'garden': [
        ('Watering that survives a heatwave',
         'How often should I water tomatoes in 35 degree weather?',
         'Deeply and less often beats a little every day: soak until water reaches 20 to 30 cm, '
         'then let the top few centimetres dry. Frequent shallow watering keeps roots near the '
         'surface, which is exactly where the heat is worst.'),
        ('Soil that dries out too fast',
         'My raised bed dries within a day.',
         'Too much drainage and no mulch. Compost raises water retention, and a few centimetres of '
         'mulch on top cuts evaporation by roughly half. Both are cheap; the mulch is the one '
         'people skip and the one with the fastest visible effect.'),
    ],
    'fitness': [
        ('Returning to running after a break',
         'How do I start running again after two years off?',
         'Cap it by time, not distance, and keep the first three weeks conversational. Injury on a '
         'return almost always comes from pace, not volume, and the tissues that need adapting '
         'take longer than the fitness that returns first.'),
        ('Strength work with no equipment',
         'Can I make progress with bodyweight only?',
         'For a long while, yes, by changing leverage rather than adding weight: elevate the feet, '
         'slow the eccentric, move toward single-limb versions. Progress stalls eventually on '
         'pulling movements, which is where something to hang from becomes the one purchase worth '
         'making.'),
    ],
}

CLUSTERS.update(EXTRA_CLUSTERS)

# Третий слой тем. Нужен ради объёма: у каждой пары свой заголовок, и без
# достаточного пула список переписок начинает двоиться
MORE_CLUSTERS = {
    'kubernetes': [
        ('Pod that restarts without an obvious error',
         'A pod restarts every few minutes and the logs end normally.',
         'Look at the previous container, not the current one: `kubectl logs pod --previous`. A '
         'clean ending plus a restart usually means OOMKilled, which shows in '
         '`kubectl describe pod` under Last State. Memory limits are the first thing to check, '
         'requests the second.'),
        ('Requests and limits that actually work',
         'Should requests equal limits?',
         'For memory, yes: memory is incompressible, so a limit above the request means the pod '
         'gets killed rather than throttled. For CPU, set requests and leave limits off unless you '
         'need hard isolation, because CPU limits throttle in ways that look like random latency.'),
        ('Rolling update that drops requests',
         'Deploys cause a handful of 502s every time.',
         'The old pod stops accepting before the proxy stops sending. Add a readiness probe and a '
         'preStop sleep of a few seconds:\n\n'
         '```yaml\nlifecycle:\n  preStop:\n    exec:\n      command: ["sleep", "5"]\n```\n\n'
         'That gap gives the endpoint controller time to remove the pod before the process exits.'),
        ('Secrets that are not really secret',
         'Kubernetes secrets are just base64. Is that a problem?',
         'It is, if that is the only layer. Enable encryption at rest for etcd, restrict RBAC on '
         'the secrets resource, and keep them out of the manifests in git. Base64 is an encoding, '
         'and treating it as protection is the most common misunderstanding in this area.'),
    ],
    'networking': [
        ('Diagnosing slow DNS',
         'Requests hang for exactly five seconds sometimes.',
         'A five second hang is almost always a DNS timeout, often IPv6 lookups failing before the '
         'IPv4 retry. Check with `dig +trace` and compare `getent hosts` to a direct query. In '
         'containers the usual culprit is a search domain list that turns one lookup into five.'),
        ('TLS handshake failures on an old client',
         'An old device cannot connect since we tightened TLS.',
         'Check the cipher suite overlap first:\n\n'
         '```bash\nopenssl s_client -connect example.com:443 -tls1_2 -servername example.com\n```\n\n'
         'The honest answer is often that the device cannot be supported without weakening security '
         'for everyone, which is a decision to make explicitly rather than by config drift.'),
        ('MTU problems that look like random hangs',
         'Large responses hang while small ones work.',
         'Classic MTU or path MTU discovery failure, usually with a tunnel in the path. Test by '
         'lowering the MTU on one side and retrying; if it fixes it, the real problem is ICMP being '
         'blocked somewhere, which is what breaks discovery.'),
        ('Keeping a connection alive through a proxy',
         'Long-lived connections die after 60 seconds.',
         'Something in the path has an idle timeout, and the fix is keepalives shorter than it. Set '
         'TCP keepalive on the socket and, for HTTP, send a periodic ping frame. Raising the '
         'timeout on your side alone never helps, because the proxy is the one hanging up.'),
    ],
    'typescript': [
        ('Typing an API response you do not control',
         'How do I type JSON from an external API safely?',
         'Parse, do not cast. A cast is a promise you cannot keep:\n\n'
         '```ts\nconst User = z.object({ id: z.number(), email: z.string().email() });\n'
         'type User = z.infer<typeof User>;\nconst user = User.parse(await res.json());\n```\n\n'
         'The runtime check is the point: `as User` compiles happily and fails at three in the '
         'morning instead.'),
        ('any versus unknown',
         'Is unknown really better than any?',
         'Yes, because it forces a check before use. `any` disables the checker silently and spreads '
         'through everything it touches; `unknown` keeps the value opaque until you narrow it, '
         'which is exactly the discipline you wanted when you reached for a type.'),
        ('Discriminated unions for state',
         'How do I model loading and error states without booleans?',
         'A discriminated union removes impossible states:\n\n'
         '```ts\ntype State =\n  | { status: "idle" }\n  | { status: "loading" }\n'
         '  | { status: "ok"; data: User[] }\n  | { status: "error"; message: string };\n```\n\n'
         'With three booleans you can represent loading and error simultaneously; with this you '
         'cannot, and the compiler enforces handling each case.'),
        ('Strict mode on an existing project',
         'Is turning on strict worth the errors it produces?',
         'Yes, incrementally. Turn on one flag at a time, starting with `strictNullChecks`, which '
         'finds the largest class of real bugs. Doing all of them at once produces a number so '
         'large that the team stops looking at it.'),
    ],
    'rust': [
        ('Borrow checker fighting a simple loop',
         'I cannot mutate a vector while iterating over it.',
         'That is the rule doing its job: a resize would invalidate the iterator. Collect the '
         'changes and apply after, or iterate by index, or use `retain` when you are removing:\n\n'
         '```rust\nitems.retain(|item| item.keep);\n```\n\n'
         'In C++ the same code compiles and reads freed memory occasionally, which is the '
         'difference being paid for.'),
        ('When to reach for clone',
         'Is cloning to satisfy the compiler bad practice?',
         'It is a legitimate first draft. Get it working with clones, measure, then remove the ones '
         'that matter. Fighting lifetimes on a prototype costs days and usually ends with the same '
         'structure you would have reached by refactoring later.'),
        ('Error handling without unwrap everywhere',
         'unwrap is fine in examples but what do real programs do?',
         'Propagate with `?` and define one error type per crate boundary. `thiserror` for '
         'libraries, `anyhow` for applications is the common split: libraries need callers to match '
         'on variants, applications mostly need context and a good message.'),
    ],
    'regex': [
        ('Matching nested structures',
         'My regex for nested brackets keeps failing.',
         'Because regular expressions cannot count. Nesting needs a parser, even a ten line one '
         'with a stack. The regex that appears to work handles two levels and fails on the third, '
         'which is worse than not working at all.'),
        ('Greedy versus lazy quantifiers',
         'My pattern swallows the whole line.',
         '`.*` is greedy: it takes everything, then backtracks. Use `.*?` for the shortest match, '
         'or better, a negated class like `[^"]*` which cannot cross the delimiter at all and does '
         'not backtrack.'),
        ('Regex that is slow on long input',
         'A pattern hangs on certain inputs.',
         'Catastrophic backtracking, usually from nested quantifiers like `(a+)+`. Rewrite so each '
         'position has one way to match, or use a library with a linear-time engine. Input length '
         'alone rarely causes it; ambiguity does.'),
    ],
    'reading': [
        ('What to read after a distributed systems book',
         'Finished Designing Data-Intensive Applications. What next?',
         'Papers, in small doses: the Dynamo paper for the tradeoffs, Raft for consensus you can '
         'actually follow, and the Google SRE book for how it fails in practice. Another textbook '
         'at this point adds vocabulary rather than understanding.'),
        ('Keeping notes on technical books',
         'I read and forget. What note system survives?',
         'Notes that answer questions you had, not summaries of chapters. A chapter summary is a '
         'worse version of the book; a note that says "this is why our retry storm happened" is '
         'retrievable years later because it is attached to a real problem.'),
        ('Reading papers without a maths degree',
         'Papers lose me at the equations.',
         'Read the abstract, the conclusion, and the experimental setup first, and skip the proofs '
         'entirely on the first pass. Most of the transferable content of a systems paper is in '
         'what they measured and what surprised them.'),
    ],
    'money': [
        ('Emergency fund sizing',
         'How many months of expenses should be liquid?',
         'Three to six for a stable income, more for irregular work, and the number that matters is '
         'expenses rather than income. The common mistake is sizing it against salary, which '
         'inflates the target and delays the point where you stop worrying.'),
        ('Subscriptions that quietly accumulate',
         'Small subscriptions add up and I lose track.',
         'Audit by statement, not by memory: export a year of transactions, group by merchant, and '
         'sort by annual total. Monthly amounts hide the size; the yearly figure is the one that '
         'produces cancellations.'),
        ('Comparing a loan against paying cash',
         'Zero percent financing or pay upfront?',
         'Compare against what the cash would otherwise earn, and read the fee schedule. Genuine '
         'zero percent with no fees is cheap money and worth taking; the version with an '
         'arrangement fee and a rate that jumps after a year is a loan wearing a costume.'),
    ],
    'hardware': [
        ('Choosing an SSD for constant writes',
         'Which drive survives a write-heavy workload?',
         'Look at TBW rather than sequential speed. A consumer drive rated at 300 TBW dies years '
         'earlier than one rated at 1200 under the same load, and the fast numbers on the box '
         'describe bursts to cache, not sustained writes.'),
        ('Laptop that throttles under load',
         'Performance drops after a couple of minutes of compiling.',
         'Thermal throttling. Check the sustained clock with a monitor running, then decide between '
         'undervolting, a lower power limit that trades peak for consistency, or a cooling pad. '
         'The consistent lower clock usually finishes builds faster than the sawtooth.'),
        ('Do I need ECC memory at home',
         'Is ECC worth it for a home NAS?',
         'For a filesystem that checksums data, ECC protects the one place checksums cannot: memory '
         'between verification and write. It is not mandatory, and the honest framing is insurance '
         'whose premium is a slightly more expensive board.'),
    ],
    'cooking': [
        ('Pan sauce that separates',
         'My pan sauce breaks every time.',
         'Heat and order. Take the pan off the heat before the butter goes in, add it cold and in '
         'pieces, and swirl rather than stir. A broken sauce is usually rescued by a spoonful of '
         'cold water off the heat, whisked hard.'),
        ('Salting pasta water properly',
         'How much salt is right for pasta water?',
         'About 10 g per litre, which tastes like a mild broth. This is the only chance to season '
         'the pasta itself; salt added afterwards sits on the surface and never gets inside the '
         'starch.'),
        ('Resting meat, real or myth',
         'Does resting a steak actually matter?',
         'Yes, measurably: resting lets the temperature even out and the juices redistribute, so '
         'less liquid runs out on the board. Five minutes for a steak, twenty for a roast, and '
         'loosely covered rather than wrapped, which steams the crust away.'),
    ],
    'travel': [
        ('Packing for a week in one bag',
         'How do people fit a week into carry-on?',
         'By choosing a colour palette and doing laundry once, not by rolling more efficiently. '
         'Three tops, two bottoms and a layer covers a week; the volume that defeats people is '
         'shoes and the "just in case" category.'),
        ('Booking flights without the games',
         'Are those price prediction tools worth anything?',
         'Marginally. The reliable part is that prices rise close to departure and dip on midweek '
         'flights, both of which you can exploit without a tool. Set a price alert, book when it '
         'is acceptable, and stop watching, because the regret costs more than the difference.'),
        ('Jet lag that does not ruin the first days',
         'Any approach to jet lag that actually works?',
         'Shift the light schedule, not the sleep schedule: get bright light in the morning at the '
         'destination and avoid it in the evening. Melatonin helps at small doses taken early '
         'relative to the new night; large doses mostly make you drowsy at the wrong time.'),
    ],
}

CLUSTERS.update(MORE_CLUSTERS)

# Последний слой: доводит пул заголовков до размера архива и добавляет таблицы
# и формулы, которых в фоне почти не было
FINAL_CLUSTERS = {
    'compare': [
        ('Choosing between managed and self-hosted database',
         'Managed database or run it myself?',
         'The comparison that matters is not price per month:\n\n'
         '| | Managed | Self-hosted |\n| --- | --- | --- |\n'
         '| Cost at 100 GB | higher | lower |\n| Backups | included, tested | your job |\n'
         '| Failover | minutes | your job |\n| 3am pager | theirs | yours |\n\n'
         'Self-hosting wins on invoice and loses on the hours you cannot schedule. Below one '
         'full-time operator, managed is usually cheaper in the currency that runs out first.'),
        ('Monorepo or many repositories',
         'Is a monorepo worth it for four services?',
         'At four services the deciding factor is how often changes cross a boundary:\n\n'
         '| | Monorepo | Multi-repo |\n| --- | --- | --- |\n'
         '| Cross-cutting change | one PR | coordinated PRs |\n'
         '| CI complexity | needs filtering | simple per repo |\n'
         '| Access control | coarse | per repo |\n\n'
         'If most changes touch one service, separate repos stay simpler. If a typical feature '
         'touches three, the coordination cost outweighs everything else.'),
        ('REST or gRPC for internal services',
         'Which protocol for service to service calls?',
         'gRPC when the callers are yours and latency matters, REST when they are not:\n\n'
         '| | REST/JSON | gRPC |\n| --- | --- | --- |\n| Debuggable with curl | yes | awkward |\n'
         '| Schema enforced | optional | always |\n| Streaming | clumsy | native |\n'
         '| Browser support | direct | needs a proxy |\n\n'
         'The schema is the real difference: with JSON the contract lives in documentation, with '
         'protobuf it lives in a file that breaks the build when violated.'),
        ('Queue versus cron for background work',
         'Should scheduled jobs go through a queue?',
         'If a job can be late, a queue; if it must run at a wall-clock time, a scheduler. Mixing '
         'them produces the worst outcome: a cron entry that enqueues work which then sits behind '
         'a backlog, so the job runs on time and executes hours later.'),
        ('Feature flags versus branches',
         'Long branch or a flag behind main?',
         'Flags for anything longer than a few days. A branch that lives two weeks becomes a merge '
         'event; a flag makes the same work a series of small changes. The cost is discipline about '
         'removing flags, which is the part every team underestimates.'),
    ],
    'estimates': [
        ('Estimating a migration honestly',
         'How do I estimate a data migration with unknown data quality?',
         'Split it into three numbers: the transform you can specify, the exceptions you find in a '
         'sample, and the tail you cannot see yet. Sample a thousand rows first; the exception rate '
         'there sets the multiplier for everything else, and the multiplier is usually between two '
         'and four.'),
        ('Why estimates are always optimistic',
         'Our estimates are consistently half of reality.',
         'Because they estimate the work, not the day. A useful correction is to track a personal '
         'ratio of estimate to actual over a few months and apply it openly rather than padding '
         'silently, which reads as sandbagging when it is discovered.'),
        ('Deadlines that cannot move',
         'How do you plan when the date is fixed?',
         'Fix the date and vary the scope, explicitly and in writing, with the cut list agreed '
         'before work starts. The failure mode is holding both fixed, which does not change the '
         'outcome, only when everyone finds out.'),
        ('Buffer that does not get eaten',
         'Padding gets consumed immediately. Better approach?',
         'Keep the buffer at the project level rather than per task, and make spending it visible. '
         'Per-task padding disappears into Parkinson\'s law; a shared buffer with a burn chart '
         'stays honest because everyone sees the same number.'),
    ],
    'review': [
        ('Reviewing code without nitpicking',
         'How do I review without turning it into style comments?',
         'Automate style entirely, then the review can only be about substance. What remains worth '
         'saying: this breaks under concurrency, this loses an error, this name means something '
         'else in our codebase. If a comment could be a lint rule, make it one.'),
        ('Reviewing a change you do not understand',
         'The diff is in an area I do not know. What do I do?',
         'Say so and review what you can: tests, error handling, whether the description matches '
         'the change. An approval that means "I did not understand this" is worse than no review, '
         'and a question in the thread is often more useful than the approval would have been.'),
        ('Large pull requests nobody reviews',
         'Big PRs sit for days. How do we fix that?',
         'Make them smaller, because attention does not scale with size: a 50 line change gets real '
         'review, a 2000 line change gets a rubber stamp. Splitting by mechanical versus meaningful '
         'is the easiest cut, since the mechanical half needs eyes but not thought.'),
    ],
    'onboarding': [
        ('First week for a new developer',
         'What should a new hire do in week one?',
         'Ship something tiny on day one, then read. The order matters: a merged one-line fix '
         'teaches the whole pipeline, and the codebase reads differently once you have touched it. '
         'A week of reading first produces a person who knows the architecture and cannot deploy.'),
        ('Documentation for a project only you know',
         'What do I write down before going on holiday?',
         'The three things that break, how to tell which one it is, and who to call when it is '
         'none of them. Architecture diagrams are pleasant; runbooks are what get used at two in '
         'the morning.'),
        ('Handover that survives the handover',
         'How do I transfer ownership of a service properly?',
         'Have the new owner run the next two deploys and the next incident while you watch. '
         'Documents transfer facts, not judgement, and judgement is most of what ownership is.'),
    ],
    'privacy': [
        ('What a data export actually contains',
         'Does an export include everything a service knows about me?',
         'It includes what they classify as your data, which is narrower than what they hold. '
         'Derived profiles, inference scores and internal logs are commonly excluded. The gap is '
         'legal rather than technical, so the practical move is to compare the export against what '
         'the interface shows and note what is missing.'),
        ('Deleting an account properly',
         'Is clicking delete enough?',
         'It starts a process with a retention window, typically 30 days, during which recovery is '
         'possible and so is a breach. Export first, then delete, then check back later that the '
         'account is actually gone rather than merely hidden.'),
        ('Sharing an archive without leaking',
         'I want to share part of my archive publicly.',
         'Strip metadata from images, search the text for names, addresses and tokens, and read the '
         'result once as a stranger would. Automated redaction misses context: a date and a place '
         'together can identify someone when neither does alone.'),
    ],
    'compression': [
        ('Choosing a compression format',
         'gzip, zstd or xz for archives I keep for years?',
         'The tradeoff in one table:\n\n'
         '| | gzip | zstd | xz |\n| --- | --- | --- |\n'
         '| Compression | baseline | better | best |\n| Speed | fast | fastest | slow |\n'
         '| Decompress | fast | fastest | moderate |\n| Ubiquity | everywhere | recent | common |\n\n'
         'For long-term archives the deciding factor is not ratio but whether the format opens '
         'without installing anything in ten years, which still favours gzip for the outer layer.'),
        ('Why my compressed archive barely shrinks',
         'A folder of photos compresses to 98% of its size.',
         'JPEG and PNG are already compressed, so a second pass finds nothing and costs CPU. '
         'Compression helps text and helps structured binary; for media the win comes from '
         'deduplication instead, which is why backup tools chunk before compressing.'),
        ('Estimating how well text will compress',
         'Rough expectation for compressing JSON logs?',
         'Repetitive JSON commonly reaches 8 to 12 times with zstd, because keys repeat on every '
         'line. If you are seeing less than three, the payload is probably already encoded or '
         'encrypted somewhere inside, which is worth knowing for reasons beyond storage.'),
    ],
    'interviewing': [
        ('Take-home tasks that respect time',
         'How long should a take-home exercise be?',
         'Under three hours, with a stated cap and an explicit instruction to stop. Anything longer '
         'selects for people with free evenings rather than for skill, which is a filter most teams '
         'would reject if it were stated out loud.'),
        ('Questions to ask the interviewer',
         'What is actually worth asking at the end?',
         'Concrete process questions: how the last incident went, how long the last change took '
         'from merge to production, what happened to the previous person in this role. Culture '
         'questions get culture answers; process questions get facts.'),
        ('Salary conversation without guessing',
         'How do I answer the expected salary question?',
         'With a range anchored on evidence, and the question turned around first: asking what the '
         'band for the role is costs nothing and is answered honestly more often than people '
         'expect. If the answer is refused, that is information too.'),
    ],
    'seo': [
        ('Making a static site discoverable',
         'What actually matters for a small static site in search?',
         'Three things, in order: the title and description, the words the page uses matching the '
         'words people type, and links from places that already rank. Everything else is polish on '
         'top of those, and no amount of markup compensates when they are wrong.'),
        ('Sitemaps for a small site',
         'Is a sitemap worth it for twenty pages?',
         'It helps discovery on a new domain with no inbound links, which is exactly the situation '
         'a fresh project is in. Once pages are linked from anywhere indexed, the sitemap stops '
         'mattering much, but it costs one file to keep.'),
        ('Open Graph tags that change nothing in ranking',
         'Do social tags affect search position?',
         'No, they affect the card people see when the link is shared, which affects whether the '
         'link gets clicked and shared further. It is a click-through lever, not a ranking one, and '
         'confusing the two is why people spend a day on markup and none on the title.'),
    ],
    'errors': [
        ('Error messages people can act on',
         'What makes an error message good?',
         'It names what failed, what was expected, and what to do next. "Invalid input" fails all '
         'three; "expected a date in YYYY-MM-DD, got 12/03/2026" passes the first two and hints at '
         'the third, which is usually enough.'),
        ('Logging exceptions without noise',
         'Every handled exception ends up in the logs and drowns the real ones.',
         'Log at the level where the decision is made, once. An exception caught, handled and '
         'logged as an error is a lie about severity; if the program recovered, it is at most a '
         'warning, and if it did not, it should reach the top and be logged there with context.'),
        ('Retries that make an outage worse',
         'Our retries turned a blip into a full outage.',
         'Synchronised retries are an attack on your own service. Exponential backoff with jitter '
         'and a cap, plus a circuit breaker that stops trying entirely once failures dominate. '
         'Without jitter every client retries at the same instant, which is precisely the '
         'thundering herd.'),
    ],
    'sleep': [
        ('Waking at the same time every night',
         'I wake at 3am consistently and cannot fall back asleep.',
         'A consistent wake time points at rhythm rather than a disturbance: often alcohol earlier '
         'in the evening, a warm room, or the anticipation itself once the pattern establishes. '
         'The counterintuitive advice that works is getting out of bed after fifteen minutes so the '
         'bed does not become the place where you lie awake.'),
        ('Naps that help instead of hurting',
         'Are naps a good idea if I sleep badly at night?',
         'Short and early: twenty minutes before mid-afternoon adds alertness without eating into '
         'the night. Ninety minutes at five in the evening is a second sleep, and the night that '
         'follows pays for it.'),
    ],
}

CLUSTERS.update(FINAL_CLUSTERS)


FOLLOWUPS = [
    ('Anything that changes this at ten times the scale?',
     'At ten times the size the bottleneck moves from the operation itself to what it competes '
     'with: memory, locks and the people who have to run it. The approach stays, the batching gets '
     'smaller and the schedule matters more.'),
    ('What is the most common way people get this wrong?',
     'Doing it once and never verifying. The setup is the visible part, so it gets attention, and '
     'the check that would catch a silent failure never gets written.'),
    ('How long does this usually take in practice?',
     'An afternoon to do it properly the first time, then minutes when it recurs. Most of the first '
     'afternoon goes into discovering which of the defaults do not match your situation.'),
    ('Is there a simpler version that gets most of the benefit?',
     'Yes: do the first step, skip the automation, and revisit in a month. Most of the value is in '
     'the first step, and most of the cost is in making it repeatable before you know it is right.'),
    ('Does this still hold if I am working alone?',
     'It gets easier, not harder. A fair share of the difficulty is coordination, and that '
     'disappears. What remains is remembering your own decisions, which is what writing them down '
     'is for.'),
    ('What would you skip entirely?',
     'The reporting layer, until something forces it. It is the part that feels productive to build '
     'and the part nobody opens twice.'),
    ('Any downside worth knowing before I commit?',
     'It commits you to a format that is tedious to migrate away from later. The first weeks also '
     'look worse than doing nothing, which is when most people abandon it.'),
    ('How do I know when it stops being worth it?',
     'When you stop noticing it. If it has not surfaced a problem in six months, it is either '
     'solved or it was never the bottleneck you thought.'),
]

MODELS = ['gpt-4o', 'gpt-5', 'o3', 'gpt-5-thinking']


def node(node_id, parent, message):
    return {'id': node_id, 'message': message, 'parent': parent, 'children': []}


def message(node_id, role, parts, create_time, name=None, recipient='all', ctype='text'):
    return {
        'id': node_id,
        'author': {'role': role, 'name': name, 'metadata': {}},
        'create_time': create_time,
        'update_time': None,
        'content': {'content_type': ctype, 'parts': parts},
        'status': 'finished_successfully',
        'end_turn': True,
        'weight': 1,
        'metadata': {},
        'recipient': recipient,
    }


def tool_nodes(index, counter, parent, stamp, tool):
    reasoning_id = 'node-%04d-%02d' % (index, counter + 1)
    reasoning = message(reasoning_id, 'assistant', [], stamp, ctype='reasoning_recap')
    reasoning['content'] = {
        'content_type': 'reasoning_recap',
        'content': 'Checked the query plan, then compared index options.',
    }

    code_id = 'node-%04d-%02d' % (index, counter + 2)
    code = message(code_id, 'assistant', [], stamp + 20, recipient=tool, ctype='code')
    code['content'] = {
        'content_type': 'code',
        'language': 'python',
        'text': 'rows = run_sql("EXPLAIN (ANALYZE) SELECT ...")\nprint(rows[:3])',
    }

    output_id = 'node-%04d-%02d' % (index, counter + 3)
    output = message(output_id, 'tool', [], stamp + 40, name=tool, ctype='execution_output')
    output['content'] = {
        'content_type': 'execution_output',
        'text': 'Seq Scan on events  (cost=0.00..812431.00 rows=41203122 width=16)\n'
                '  Rows Removed by Filter: 38996878\nPlanning Time: 0.214 ms\n'
                'Execution Time: 11842.663 ms',
    }

    return [node(reasoning_id, parent, reasoning),
            node(code_id, reasoning_id, code),
            node(output_id, code_id, output)]


def build_conversation(title, started, script, index, rnd):
    mapping = {}
    root_id = 'root-%04d' % index
    mapping[root_id] = node(root_id, None, None)
    parent = root_id
    stamp = started
    counter = 0

    for step in script:
        counter += 1
        stamp += 90 + rnd.randrange(240)
        node_id = 'node-%04d-%02d' % (index, counter)
        if 'image' in step:
            msg = message(node_id, 'user', [{
                'content_type': 'image_asset_pointer',
                'asset_pointer': step['image'],
                'size_bytes': 184420, 'width': 760, 'height': 380,
            }], stamp, ctype='multimodal_text')
        elif step['role'] == 'user':
            msg = message(node_id, 'user', [step['text']], stamp)
            if step.get('attachments'):
                msg['metadata']['attachments'] = [
                    {'id': ATTACHMENT_IDS.get(item, 'file_%02d%s' % (index, chr(97 + n))),
                     'name': item, 'size': 24576, 'mime_type': 'text/csv'}
                    for n, item in enumerate(step['attachments'])]
        else:
            msg = message(node_id, 'assistant', [step['text']], stamp)

        mapping[node_id] = node(node_id, parent, msg)
        mapping[parent]['children'].append(node_id)
        parent = node_id

        if step.get('tool'):
            for extra in tool_nodes(index, counter, parent, stamp, step['tool']):
                counter += 1
                stamp += 30
                mapping[extra['id']] = extra
                mapping[parent]['children'].append(extra['id'])
                parent = extra['id']

    return {
        'title': title,
        'create_time': started,
        'update_time': stamp,
        'mapping': mapping,
        'current_node': parent,
        'conversation_id': 'demo-%08d' % (index * 7919),
        'is_archived': index % 23 == 0,
        'default_model_slug': MODELS[index % len(MODELS)],
    }


def from_question(question):
    """Заголовок из первой фразы пользователя, как это делает сам ChatGPT."""
    text = question.split('\n')[0].rstrip('?.!')
    if len(text) > 64:
        text = text[:64].rsplit(' ', 1)[0]
    return text[0].upper() + text[1:]


def pick_title(title, question, pairs, position, used):
    """Выбор незанятого заголовка из естественных источников, без искусственных суффиксов."""
    candidates = [title, from_question(question)]
    for step in (1, 2, 3):
        neighbour = pairs[(position + step) % len(pairs)]
        candidates.append(neighbour[0])
        candidates.append(from_question(neighbour[1]))
    for candidate in candidates:
        if candidate not in used:
            used.add(candidate)
            return candidate
    return title


def day_to_stamp(today, days_ago, rnd):
    day = today - datetime.timedelta(days=days_ago)
    seconds = rnd.randrange(8 * 3600, 23 * 3600)
    return int(datetime.datetime.combine(
        day, datetime.time(), datetime.timezone.utc).timestamp()) + seconds


def spread_day(days_ago, taken, limit=4):
    """Разведение дат по соседним дням.

    Степенное распределение сгущает переписки у сегодняшнего дня, и без этого
    ограничения десяток из них садится на одну дату
    """
    while taken.get(days_ago, 0) >= limit:
        days_ago += 1
    taken[days_ago] = taken.get(days_ago, 0) + 1
    return days_ago


def main():
    rnd = random.Random(SEED)
    today = datetime.date.today()
    conversations = []
    index = 0

    # Витрина занимает последние полгода, чтобы попадаться на первом экране списка
    for offset, (title, script) in enumerate(SHOWCASE):
        days_ago = 8 + offset * 12 + rnd.randrange(6)
        conversations.append(build_conversation(
            title, day_to_stamp(today, days_ago, rnd), script, index, rnd))
        index += 1

    # Один длинный тред: показывает оглавление вопросов в правой колонке
    long_script = []
    for topic in ('postgres', 'python', 'observability', 'testing'):
        for title, question, answer in CLUSTERS[topic]:
            long_script.append(user(question))
            long_script.append(bot(answer))
    conversations.append(build_conversation(
        'Everything I asked while rewriting the ingest service',
        day_to_stamp(today, 21, rnd), long_script, index, rnd))
    index += 1

    second_long = []
    for topic in ('archives', 'security', 'linux', 'home', 'photography'):
        for title, question, answer in CLUSTERS[topic]:
            second_long.append(user(question))
            second_long.append(bot(answer))
    conversations.append(build_conversation(
        'Setting up the home archive, start to finish',
        day_to_stamp(today, 47, rnd), second_long, index, rnd))
    index += 1

    # Фон: каждая пара из кластера один раз становится началом переписки,
    # продолжения берутся из соседних пар той же темы, поэтому ответы всегда
    # отвечают на свой вопрос
    anchors = []
    for topic, pairs in CLUSTERS.items():
        for position, pair in enumerate(pairs):
            anchors.append((topic, position, pair))
    rnd.shuffle(anchors)
    used_titles = {conv['title'] for conv in conversations}
    taken_days = {}

    image_pointers = ['sediment://%s' % fid for fid, _, _ in ASSETS]
    while len(conversations) < TOTAL:
        topic, position, (title, question, answer) = anchors[len(conversations) % len(anchors)]
        pairs = CLUSTERS[topic]
        script = [user(question), bot(answer)]

        for step in range(rnd.randrange(0, 3)):
            nxt = pairs[(position + step + 1) % len(pairs)]
            script.append(user(nxt[1]))
            script.append(bot(nxt[2]))

        for _ in range(rnd.randrange(0, 2)):
            followup = FOLLOWUPS[rnd.randrange(len(FOLLOWUPS))]
            script.append(user(followup[0]))
            script.append(bot(followup[1]))

        if rnd.random() < 0.12:
            script.insert(2, image(image_pointers[index % len(image_pointers)]))
        if rnd.random() < 0.06:
            script[1]['tool'] = 'python'

        shown = pick_title(title, question, pairs, position, used_titles)
        days_ago = spread_day(int(SPAN_DAYS * (rnd.random() ** 1.7)), taken_days)
        conversations.append(build_conversation(
            shown, day_to_stamp(today, days_ago, rnd), script, index, rnd))
        index += 1

    conversations.sort(key=lambda item: item['update_time'])

    shards = [conversations[i:i + SHARD_SIZE] for i in range(0, len(conversations), SHARD_SIZE)]
    manifest = []
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as zf:
        for number, shard in enumerate(shards):
            name = 'conversations-%03d.json' % number
            body = json.dumps(shard, ensure_ascii=False, separators=(',', ':'))
            zf.writestr(name, body)
            manifest.append({'name': name, 'size_bytes': len(body.encode('utf-8'))})

        names = {}
        if Image is not None:
            for fid, filename, draw in ASSETS:
                buffer = io.BytesIO()
                draw().save(buffer, format='PNG')
                zf.writestr(fid + '.dat', buffer.getvalue())
                names[fid + '.dat'] = filename
        csv = ('category,amount\n'
               'groceries,820\n'
               'eating out,640\n'
               'transport,410\n'
               'subscriptions,380\n')
        zf.writestr(BUDGET_ASSET + '.dat', csv.encode('utf-8'))
        names[BUDGET_ASSET + '.dat'] = 'budget-2025.csv'
        names[MISSING_ASSET + '.dat'] = 'diagram-that-expired.png'
        zf.writestr('conversation_asset_file_names.json', json.dumps(names, indent=1))
        zf.writestr('export_manifest.json', json.dumps(
            {'logical_files': {'conversations.json': {'files': manifest}}}, indent=1))
        zf.writestr('user.json', json.dumps(
            {'id': 'user-demo', 'email': 'demo@example.com', 'chatgpt_plus_user': True}, indent=1))
        zf.writestr('chat.html', '<html><body><div id="root"></div></body></html>')

    print('conversations:', len(conversations), '| shards:', len(shards),
          '| assets:', len(ASSETS) if Image else 0)
    print('export:', os.path.abspath(OUT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
