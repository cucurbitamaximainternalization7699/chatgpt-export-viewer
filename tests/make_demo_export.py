"""Generate a fake ChatGPT export for demos, screenshots and tests.

Usage:
    python3 tests/make_demo_export.py [output.zip]

The result mirrors the official export layout: sharded conversations,
extension-less .dat assets and an asset name index.
"""

import io
import json
import os
import sys
import zipfile

OUT = sys.argv[1] if len(sys.argv) > 1 else 'demo-export.zip'
SHARD_SIZE = 20
START = 1717200000

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
]

MISSING_ASSET = 'file_9f8e7d6c5b4a3928'
BUDGET_ASSET = 'file_08a'


def user(text, attachments=None):
    return {'role': 'user', 'text': text, 'attachments': attachments or []}


def bot(text, tool=None):
    return {'role': 'assistant', 'text': text, 'tool': tool}


def image(pointer):
    return {'role': 'user', 'image': pointer}


CONVERSATIONS = [
    ('Slow PostgreSQL query on a 40M row table', 0, [
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
    ]),
    ('Gradient descent, but explain the math', 4, [
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
    ]),
    ('Reading a ChatGPT export without losing your mind', 9, [
        user('I exported my data and got a 700 MB zip. conversations.json is one single line. '
             'What do people normally do with this?'),
        bot('The file is a JSON array of conversations. Each conversation has a `mapping` of nodes, '
            'and each node points at its parent, so the visible thread is the chain from '
            '`current_node` back to the root.\n\nThree things surprise everyone the first time:\n\n'
            '- edits and regenerations create branches, so the file holds more messages than the app shows\n'
            '- attachments live outside the JSON, under names that no longer carry an extension\n'
            '- exports above a certain size arrive split across `conversations-000.json` and friends'),
        image('sediment://file_6f7a8b9c0d1e2f3a'),
        user('Is there a way to just read it offline?'),
        bot('Convert it once into static HTML and open it from disk. No server, no upload, and the '
            'result keeps working when the original service is gone.'),
    ]),
    ('Sourdough starter refuses to rise', 14, [
        user('Day 6 and my starter barely doubles. Room is about 19C.'),
        bot('19C is the main suspect. Fermentation roughly halves in speed for every 5 degrees you '
            'drop, so a starter that doubles in 5 hours at 24C can take 10 to 12 hours at 19C.\n\n'
            'Before changing the recipe, try moving it somewhere warmer, feeding at 1:2:2 and giving '
            'it a full 12 hours before judging.'),
        image('sediment://file_4d5e6f7a8b9c0d1e'),
        bot('That curve is normal for a young starter: the peak is late and shallow. It usually '
            'sharpens up around day 10 once the culture stabilises.'),
    ]),
    ('Regex for parsing nginx access logs', 20, [
        user('Need a regex that pulls method, path and status out of nginx combined format.'),
        bot('```\n^(?P<ip>\\S+) \\S+ \\S+ \\[(?P<time>[^\\]]+)\\] '
            '"(?P<method>[A-Z]+) (?P<path>[^"]*?) HTTP/[\\d.]+" (?P<status>\\d{3}) (?P<size>\\d+|-)\n```\n\n'
            'Two notes. The path group is lazy so a quote inside the query string does not swallow the '
            'rest of the line, and `size` can be a dash for requests that returned no body.'),
        user('It fails on lines where the request is malformed and there is no HTTP version.'),
        bot('Make the version optional and allow the whole request to fall back to a raw capture:\n\n'
            '```\n"(?P<request>[^"]*)"\n```\n\nThen parse `request` in a second step. Log lines are '
            'user controlled, so a two stage parse survives more than one heroic pattern.'),
    ]),
    ('Three days in Lisbon, walking distances', 27, [
        user('Planning three days in Lisbon in October. I walk a lot, no car. What would you do?'),
        bot('Day 1, Baixa and Alfama. Start at Praca do Comercio, walk up through Alfama to Miradouro '
            'da Senhora do Monte. About 6 km with a lot of stairs.\n\n'
            'Day 2, Belem. Tram 15 out, then the monastery, the tower and the modern art museum. '
            'Walking is flat here, roughly 8 km.\n\n'
            'Day 3, Principe Real and Bairro Alto. Botanical garden, then down to Cais do Sodre for '
            'dinner. Around 5 km, mostly downhill.'),
        user('Is the tram worth it or is it a tourist trap?'),
        bot('Tram 28 is genuinely pretty and genuinely crowded. If you want the ride, board at '
            'Campo de Ourique rather than Martim Moniz, where the queue starts.'),
    ]),
    ('Docker compose setup for local development', 33, [
        user('I want postgres, redis and my api in one compose file, with the api reloading on change.'),
        bot('```yaml\nservices:\n  db:\n    image: postgres:16\n    environment:\n      '
            'POSTGRES_PASSWORD: local\n    ports: ["5432:5432"]\n    volumes: ["pgdata:/var/lib/postgresql/data"]\n'
            '  cache:\n    image: redis:7\n  api:\n    build: .\n    command: uvicorn app:app --reload --host 0.0.0.0\n'
            '    volumes: [".:/code"]\n    depends_on: [db, cache]\n    ports: ["8000:8000"]\n\nvolumes:\n  pgdata:\n```\n\n'
            '`depends_on` only waits for the container to start, not for postgres to accept '
            'connections, so keep a retry in the application startup.', 'python'),
        image('sediment://file_3c4d5e6f7a8b9c0d'),
    ]),
    ('Why is my container image 1.2 GB', 38, [
        user('Python image ballooned to 1.2 GB. Base is python:3.12, I install from requirements.txt.'),
        bot('Three usual causes, in order of size:\n\n'
            '1. The full `python:3.12` image is about 1 GB on its own. `python:3.12-slim` is around 130 MB.\n'
            '2. Build tools stay in the final layer. Install them, build wheels, then drop them in a '
            'second stage.\n3. Layer caching keeps deleted files alive. Deleting in a later `RUN` does '
            'not shrink the earlier layer.\n\nA two stage build usually lands between 180 and 250 MB.'),
    ]),
    ('Monthly spending review', 45, [
        user('Here is my spending by category for last year. Anything obviously off?',
             ['budget-2025.csv']),
        image('sediment://file_5e6f7a8b9c0d1e2f'),
        bot('Two things stand out. Groceries and eating out together are 46 percent of the total, '
            'which is high even for a city budget. And the subscriptions line grew every quarter '
            'without a step change, which usually means small recurring additions nobody cancels.'),
        user('What would you cut first?'),
        bot('Nothing yet. Track one month at category level before cutting anything, because the '
            'first pass at a budget usually reveals a misclassification rather than a real problem.'),
    ]),
    ('CAP theorem in plain words', 52, [
        user('Explain CAP without the usual triangle picture.'),
        bot('When the network splits, you get to keep serving requests or you get to keep every '
            'replica identical, not both.\n\n'
            '| Choice | What you keep | What you lose |\n| --- | --- | --- |\n'
            '| CP | one consistent view | availability during a partition |\n'
            '| AP | every node answers | replicas can disagree for a while |\n\n'
            'Consistency and availability without partitions is not a trade off at all, which is why '
            'the triangle confuses people.'),
    ]),
    ('Making sense of an old research folder', 58, [
        user('I have 400 notes from two years of reading, no structure. Where do I even start?'),
        bot('Sort by what you can act on, not by topic. Three buckets: notes that answer a question '
            'you still have, notes that only make sense with the source next to them, and notes you '
            'kept because they felt important.\n\nThe third bucket is usually half the folder and can '
            'be archived without loss.'),
        user('That last part stings a bit.'),
        bot('It is the most common outcome, and it is not wasted effort. Reading changed what you '
            'know even when the note itself never gets reopened.'),
    ]),
    ('Image that never made it into the export', 63, [
        user('Can you show me the diagram again?'),
        image('sediment://' + MISSING_ASSET),
        bot('That image was generated in the session, but exports do not always include generated '
            'files. If it is missing from your archive, the reference stays in the conversation while '
            'the file itself is gone.'),
    ]),
]

FILLER = [
    ('Naming things in a small codebase', 'How strict should naming conventions be for a two person project?'),
    ('Choosing a chart type for survey results', 'Bar chart or stacked bar for a five point scale?'),
    ('Rewriting a cover letter', 'Can you make this cover letter less generic?'),
    ('Keyboard shortcuts I keep forgetting', 'Give me the ten most useful shortcuts in VS Code.'),
    ('Explaining recursion to a beginner', 'How do I explain recursion without the factorial example?'),
    ('Picking a backup drive', 'External SSD or NAS for 2 TB of photos?'),
    ('Weekly meal plan for two', 'Plan a week of dinners, nothing that takes over 40 minutes.'),
    ('Reading list on distributed systems', 'What should I read after the Designing Data-Intensive book?'),
    ('Migrating from Bootstrap to plain CSS', 'Is dropping Bootstrap worth it for a small site?'),
    ('Setting up a home server quietly', 'Which mini PC is quiet enough for a bedroom?'),
    ('Understanding p-values', 'What does a p-value actually tell me?'),
    ('Fixing a wobbly desk', 'My standing desk wobbles at full height. Ideas?'),
    ('Learning to sketch at 35', 'Is it realistic to learn drawing as an adult?'),
    ('Comparing two job offers', 'How do I compare a startup offer against a corporate one?'),
    ('Cold brew ratios', 'What coffee to water ratio for cold brew?'),
    ('Backing up a phone properly', 'What is a sane backup routine for a phone?'),
    ('Tuning a bicycle derailleur', 'Rear derailleur skips on the third gear.'),
    ('Reducing meeting load', 'How do I cut a team from twelve meetings a week?'),
    ('Explaining Unicode normalization', 'Why do two identical strings compare as different?'),
    ('First week with a new language', 'How do I structure the first week learning Go?'),
]


OPENERS = [
    'The honest answer about %s is that the gap between the options is smaller than it looks from '
    'the outside. Here is how I would decide, and what I would ignore.',
    'There are two defensible answers to %s, and choosing between them comes down to how often you '
    'expect to revisit the decision.',
    'Most advice about %s is written for a median case that is not yours, so let me split it.',
    'With %s, start from the constraint that is hardest to change later. The rest follows.',
    'Short version on %s: pick the option you can undo. Long version below.',
    'People overthink %s. The failure mode is almost always operational, not technical.',
]

FOLLOWUPS = [
    'What would change your answer here?',
    'Any downside I should know about before committing?',
    'How long does this usually take in practice?',
    'Is there a simpler version that gets most of the benefit?',
    'What is the most common mistake people make with this?',
    'Does that still hold if I am doing it alone?',
    'What would you skip entirely?',
    'How do I know when it stops being worth it?',
]

REPLIES = [
    'Cost, mostly. At half the budget you keep the same approach for %s and accept a slower '
    'recovery when something breaks.',
    'One downside worth naming: %s locks you into a format that is annoying to migrate away from. '
    'The first month also looks worse than doing nothing, which is when people quit.',
    'A weekend to set up %s, then about twenty minutes a month. The setup is front loaded because '
    'the defaults rarely match what you need.',
    'Yes. Do the first half of %s, skip the automation, revisit in a month. Most of the value is in '
    'the first step and most of the cost in the second.',
    'Optimising the measurable part of %s instead of the part that actually hurts.',
    'Alone it is easier, not harder. Half the difficulty in %s is coordination, and that disappears.',
    'The scheduling. Everything else in %s earns its keep, but the schedule turns into a chore '
    'nobody follows by week three.',
    'When you stop noticing it. If %s has not surfaced a problem in six months, it is either solved '
    'or it was never the bottleneck.',
    'Write down the failure you are guarding against. Half the time the answer to %s changes once '
    'the failure is named out loud.',
    'Not much. The difference shows up at ten times your current scale, and you will rebuild %s by '
    'then anyway.',
    'Start with the boring version of %s, measure for a month, then decide whether the interesting '
    'one earns the complexity.',
    'Treating %s as a one time decision. It is a default you revisit, not a door you close.',
    'Two hours to something that works for %s, another day to something you are not embarrassed by.',
    'Nothing structural. I would only drop the reporting side of %s until you actually miss it.',
]


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
    reasoning_id = 'node-%03d-%02d' % (index, counter + 1)
    reasoning = message(reasoning_id, 'assistant', [], stamp, ctype='reasoning_recap')
    reasoning['content'] = {
        'content_type': 'reasoning_recap',
        'content': 'Checked the query plan, then compared index options.',
    }

    code_id = 'node-%03d-%02d' % (index, counter + 2)
    code = message(code_id, 'assistant', [], stamp + 20, recipient=tool, ctype='code')
    code['content'] = {
        'content_type': 'code',
        'language': 'python',
        'text': 'rows = run_sql("EXPLAIN (ANALYZE) SELECT ...")\nprint(rows[:3])',
    }

    output_id = 'node-%03d-%02d' % (index, counter + 3)
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


def build_conversation(title, day_offset, script, index):
    started = START + day_offset * 86400 + index * 900
    mapping = {}
    root_id = 'root-%03d' % index
    mapping[root_id] = node(root_id, None, None)
    parent = root_id
    stamp = started
    counter = 0

    for step in script:
        counter += 1
        stamp += 90
        node_id = 'node-%03d-%02d' % (index, counter)
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
                    {'id': 'file_%02d%s' % (index, chr(97 + n)), 'name': item,
                     'size': 24576, 'mime_type': 'text/csv'}
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
        'is_archived': index % 17 == 0,
        'default_model_slug': 'gpt-5',
    }


def main():
    conversations = []
    for index, (title, day, script) in enumerate(CONVERSATIONS):
        conversations.append(build_conversation(title, day, script, index))

    for index, (title, question) in enumerate(FILLER, start=len(CONVERSATIONS)):
        topic = title.lower()
        script = [user(question), bot(OPENERS[index % len(OPENERS)] % topic)]
        for turn in range(1 + index % 3):
            step = index * 3 + turn
            script.append(user(FOLLOWUPS[step % len(FOLLOWUPS)]))
            script.append(bot(REPLIES[step % len(REPLIES)] % topic))
        conversations.append(build_conversation(title, 3 + index * 11, script, index))

    conversations.sort(key=lambda item: item['update_time'])

    shards = [conversations[i:i + SHARD_SIZE] for i in range(0, len(conversations), SHARD_SIZE)]
    manifest = []
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as zf:
        for index, shard in enumerate(shards):
            name = 'conversations-%03d.json' % index
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
