"""Build a static, offline site from a ChatGPT data export.

Usage:
    python3 build_site.py export.zip [output-dir]
    python3 build_site.py path/to/conversations-dir [output-dir]

The optional --seo <base-url> adds description, canonical and Open Graph tags.
It is meant for the public demo build; a personal archive stays without them.
"""

import codecs
import datetime
import html
import json
import os
import re
import shutil
import sys
import zipfile
from collections import Counter
from urllib.parse import quote

CITE_PAIR = re.compile('\ue200.*?\ue201', re.S)
PUA = re.compile('[\ue000-\uf8ff]')
BRACKET_MARK = re.compile('\u3010(?=[^\u3011]{0,120}(?:\u2020|turn\d))[^\u3011]{0,120}\u3011')
CITE_LEFTOVER = re.compile(r'\b(?:file)?cite\s*turn\w*')
MATH_BLOCK = re.compile(r'\\\[.+?\\\]', re.S)
MATH_INLINE = re.compile(r'\\\(.+?\\\)', re.S)
IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}
RAW_HTML = re.compile(r'<(/?)(details|summary)(\s[^>]*)?>', re.I)
CANVAS_MARK = re.compile(r'^:::(?:\s*$|[A-Za-z][\w-]*\s*\{?\s*$|[A-Za-z][\w-]*\{)')
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

BASE = os.path.dirname(os.path.abspath(__file__))
FILES = os.path.join(BASE, 'files')
SITE = os.path.join(BASE, 'site')

SEO_BASE = ''
SEO_DESCRIPTION = ('Read a ChatGPT data export offline: full-text search across every message, '
                   'inline images, rendered LaTeX. Handles exports split into conversations-000.json '
                   'shards and attachments saved without a file extension.')

MONTHS = ['', 'January', 'February', 'March', 'April', 'May', 'June',
          'July', 'August', 'September', 'October', 'November', 'December']

ICON_MSG = ('<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M20.5 12.4c0 3.8-3.8 6.9-8.5 6.9-.9 0-1.8-.1-2.6-.3L4 21l1.4-3.6C4 16.1 3.5 14.3 '
            '3.5 12.4c0-3.8 3.8-6.9 8.5-6.9s8.5 3.1 8.5 6.9z"/></svg>')

ICON_PIC = ('<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linejoin="round" aria-hidden="true">'
            '<rect x="3.2" y="5" width="17.6" height="14" rx="2"/>'
            '<circle cx="8.6" cy="10.2" r="1.4"/><path d="M20.8 15.6 16 10.8l-6.4 6.4"/></svg>')

try:
    from PIL import Image
except ImportError:
    Image = None

IMAGE_MAX_H = 440
TEXT_LIMIT = 20000


def size_attrs(name):
    if Image is None:
        return ''
    try:
        with Image.open(os.path.join(FILES, name)) as img:
            width, height = img.size
    except Exception:
        return ''
    if not width or not height:
        return ''
    shown = width if height <= IMAGE_MAX_H else max(1, round(width * IMAGE_MAX_H / height))
    return (' width="' + str(width) + '" height="' + str(height)
            + '" style="--iw:' + str(shown) + 'px"')


def plural(count, forms):
    return forms[0] if abs(count) == 1 else forms[1]


def nested_shard_archives(archive, names):
    extra = []
    routes = {}
    for name in names:
        if not name.lower().endswith('.zip'):
            continue
        stream = None
        nested = None
        try:
            stream = archive.open(name)
            nested = zipfile.ZipFile(stream)
            inner_names = nested.namelist()
        except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile):
            if nested is not None:
                nested.close()
            if stream is not None:
                stream.close()
            continue

        if not any(SHARD_NAME.match(inner.split('/')[-1]) for inner in inner_names):
            nested.close()
            stream.close()
            continue

        for inner in inner_names:
            if inner.endswith('/'):
                continue
            virtual = name + '/' + inner
            extra.append(virtual)
            routes[virtual] = (nested, inner)
    return extra, routes


def export_reader(source):
    if zipfile.is_zipfile(source):
        archive = zipfile.ZipFile(source)
        names = archive.namelist()
        if shard_names(names, archive.open):
            return names, archive.open, None

        extra, routes = nested_shard_archives(archive, names)
        if not routes:
            return names, archive.open, None

        def nested_opener(name):
            route = routes.get(name)
            if route is None:
                return archive.open(name)
            return route[0].open(route[1])

        return names + extra, nested_opener, None
    names = []
    for root, _, files in os.walk(source):
        for name in files:
            names.append(os.path.relpath(os.path.join(root, name), source).replace(os.sep, '/'))
    return names, lambda name: open(os.path.join(source, name.replace('/', os.sep)), 'rb'), source


def extract_assets(names, opener, out_dir, root=None):
    os.makedirs(out_dir, exist_ok=True)
    titles = {}
    for name in names:
        if name.split('/')[-1] != 'conversation_asset_file_names.json':
            continue
        try:
            with opener(name) as raw:
                found = json.loads(raw.read().decode('utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(found, dict):
            titles.update(found)

    mapping = {}
    for name in names:
        if name.endswith('/'):
            continue
        base = name.split('/')[-1]
        match = ASSET_ID.match(base)
        if not match:
            continue
        fid = match.group(0)
        if fid in mapping:
            continue
        original = (titles.get(base) or titles.get(fid + '.dat') or base).split('/')[-1]
        with opener(name) as raw:
            head = raw.read(16)
            stem = slugify(os.path.splitext(original)[0])[:60] or 'file'
            out_name = fid + '__' + stem + asset_extension(head, original)
            target = os.path.join(out_dir, out_name)
            if root and not os.path.exists(target):
                try:
                    os.link(os.path.join(root, name.replace('/', os.sep)), target)
                    mapping[fid] = out_name
                    continue
                except OSError:
                    pass
            with open(target, 'wb') as fh:
                fh.write(head)
                shutil.copyfileobj(raw, fh)
        mapping[fid] = out_name
    return mapping


def iter_conversations(names, opener):
    for shard in shard_names(names, opener):
        with opener(shard) as raw:
            for conv in stream_json_array(raw):
                yield conv


SHARD_NAME = re.compile(r'^conversations(?:-\d+)?\.json$')
ASSET_ID = re.compile(r'file[-_][A-Za-z0-9]+')


SIGNATURES = (
    (b'\x89PNG\r\n\x1a\n', '.png'),
    (b'\xff\xd8\xff', '.jpg'),
    (b'GIF87a', '.gif'),
    (b'GIF89a', '.gif'),
    (b'BM', '.bmp'),
    (b'%PDF', '.pdf'),
    (b'PK\x03\x04', '.zip'),
)


def stream_json_array(handle, chunk_size=1 << 20):
    decoder = codecs.getincrementaldecoder('utf-8')('replace')
    buffer = ''
    scan = 0
    depth = 0
    item_depth = None
    start = -1
    in_string = False
    escaped = False
    while True:
        piece = handle.read(chunk_size)
        if not piece:
            break
        buffer += decoder.decode(piece) if isinstance(piece, bytes) else piece
        while scan < len(buffer):
            char = buffer[scan]
            if in_string:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char in '{[':
                if char == '[' and item_depth is None:
                    item_depth = depth + 1
                elif char == '{' and depth == item_depth and start < 0:
                    start = scan
                depth += 1
            elif char in '}]':
                depth -= 1
                if char == '}' and depth == item_depth and start >= 0:
                    try:
                        yield json.loads(buffer[start:scan + 1])
                    except ValueError as err:
                        print('skipped conversation:', err)
                    buffer = buffer[scan + 1:]
                    scan = -1
                    start = -1
            scan += 1


def shard_names(names, opener):
    if 'export_manifest.json' in names:
        try:
            with opener('export_manifest.json') as raw:
                manifest = json.loads(raw.read().decode('utf-8'))
            listed = manifest['logical_files']['conversations.json']['files']
            picked = [row['name'] if isinstance(row, dict) else row for row in listed]
            found = [name for name in picked if name in names]
            if found:
                return sorted(found)
        except (OSError, KeyError, ValueError, TypeError):
            pass
    return sorted(name for name in names if SHARD_NAME.match(name.split('/')[-1]))


def asset_extension(head, fallback_name):
    for signature, suffix in SIGNATURES:
        if head.startswith(signature):
            return suffix
    if head[:4] == b'RIFF':
        if head[8:12] == b'WEBP':
            return '.webp'
        if head[8:12] == b'WAVE':
            return '.wav'
    stripped = head.lstrip()[:5].lower()
    if stripped.startswith(b'<svg') or stripped.startswith(b'<?xml'):
        return '.svg'
    guess = os.path.splitext(fallback_name or '')[1].lower()
    return guess if guess and len(guess) <= 6 else '.bin'


def pointer_id(raw):
    for prefix in ('sediment://', 'file-service://'):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    if '#' in raw:
        for part in raw.split('#'):
            if part.startswith('file_') or part.startswith('file-'):
                return part
        return None
    return raw


def slugify(text, limit=60):
    text = (text or 'untitled').lower()
    text = re.sub(r'[^\w\s-]', '', text, flags=re.UNICODE)
    text = re.sub(r'[\s_]+', '-', text).strip('-')
    return text[:limit].strip('-') or 'chat'


def is_marker(value):
    return any(0xE000 <= ord(ch) <= 0xF8FF or ch in '\u3010\u3011' for ch in value)


def clean_citations(text, refs):
    for ref in refs or []:
        marker = ref.get('matched_text')
        if not marker or not is_marker(marker):
            continue
        text = text.replace(marker, ref.get('alt') or '')
    text = CITE_PAIR.sub('', text)
    text = PUA.sub('', text)
    text = BRACKET_MARK.sub('', text)
    text = CTRL.sub('', text)
    return CITE_LEFTOVER.sub('', text)


def md_to_html(text):
    if not text:
        return ''
    blocks = []

    def code_block(info, code):
        info = (info or '').strip()
        if info and not re.fullmatch(r'[\w+.#-]+', info):
            head, _, rest = info.partition(' ')

            if re.fullmatch(r'[A-Za-z][\w+.#-]*', head) and re.fullmatch(r'(?:\s*[\w-]+="[^"]*")+', rest):
                info = head
            else:
                code = info + '\n' + code
                info = ''
        if not code.strip():
            return ''
        cls = ' class="lang-' + html.escape(info) + '"' if info else ''
        blocks.append('<pre><code' + cls + '>' + html.escape(code) + '</code></pre>')
        return '\x00BLOCK' + str(len(blocks) - 1) + '\x00'

    text = re.sub(r'```([^\n]*)\n(.*?)```',
                  lambda m: code_block(m.group(1), m.group(2)), text, flags=re.S)


    if '```' in text:
        at = text.index('```')
        rest = text[at + 3:]
        line_end = rest.find('\n')
        info = rest[:line_end] if line_end >= 0 else rest
        code = rest[line_end + 1:] if line_end >= 0 else ''
        text = text[:at] + code_block(info, code)

    def stash_math(match, tag):
        raw = match.group(0)
        blocks.append('<' + tag[0] + ' class="' + tag[1] + '">' + html.escape(raw) + '</' + tag[0] + '>')
        return '\x00BLOCK' + str(len(blocks) - 1) + '\x00'

    def stash_html(match):
        closing, tag, attrs = match.group(1), match.group(2).lower(), match.group(3) or ''
        if closing:
            kept = '</' + tag + '>'
        else:
            open_state = tag == 'details' and re.search(r'(?:^|\s)open(?:[\s=]|$)', attrs, re.I)
            kept = '<' + tag + (' open' if open_state else '') + '>'
        blocks.append(kept)
        return '\x00BLOCK' + str(len(blocks) - 1) + '\x00'

    text = RAW_HTML.sub(stash_html, text)
    text = MATH_BLOCK.sub(lambda m: stash_math(m, ('span', 'math-block')), text)
    text = MATH_INLINE.sub(lambda m: stash_math(m, ('span', 'math-inline')), text)
    text = html.escape(text)

    out = []
    stack = []
    li_open = []
    in_quote = False
    table = []
    para = []

    def close_item():
        if li_open and li_open[-1]:
            out.append('</li>')
            li_open[-1] = False

    def close_list():
        close_item()
        out.append('</' + stack.pop() + '>')
        li_open.pop()

    def close_lists(depth=0):
        while len(stack) > depth:
            close_list()

    def open_list(tag):
        if stack and not li_open[-1]:
            out.append('<li>')
            li_open[-1] = True
        out.append('<' + tag + '>')
        stack.append(tag)
        li_open.append(False)

    def close_quote():
        nonlocal in_quote
        if in_quote:
            out.append('</blockquote>')
            in_quote = False

    def flush_para():
        if not para:
            return
        joined = '\n'.join(para)
        para.clear()
        out.append('<p>' + inline(joined).replace('\n', '<br>') + '</p>')

    def inline(s):
        spans = []

        def keep_code(match):
            spans.append('<code>' + match.group(1) + '</code>')
            return '\x01CODE' + str(len(spans) - 1) + '\x01'

        s = re.sub(r'`([^`]+)`', keep_code, s)
        s = re.sub(r'!\[([^\]]*)\]\((https?://[^)\s]+)\)',
                   r'<a href="\2" target="_blank" rel="noreferrer">\1</a>', s)
        s = re.sub(r'!\[([^\]]*)\]\((?!https?://)([^)\s]*)\)',
                   r'<span class="nolink" title="\2">\1</span>', s)
        s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s, flags=re.S)
        s = re.sub(r'(?<!\*)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)', r'<em>\1</em>', s)
        s = re.sub(r'\[([^\]]*)\]\((https?://[^)\s]+)\)',
                   r'<a href="\2" target="_blank" rel="noreferrer">\1</a>', s)

        s = re.sub(r'\[\s*\]\(\s*\)', '', s)
        s = re.sub(r'\[([^\]]+)\]\((?!https?://)([^)\s]*)\)',
                   r'<span class="nolink" title="\2">\1</span>', s)

        s = re.sub(r'(?<![">=\w])(https?://(?:(?!&quot;|&gt;|&lt;|&amp;quot;)[^\s<>"])+?)([.,;:!?)\]]*)(?=\s|$)',
                   r'<a href="\1" target="_blank" rel="noreferrer">\1</a>\2', s)
        for n, span in enumerate(spans):
            s = s.replace('\x01CODE' + str(n) + '\x01', span)
        return s

    def flush_table():
        if not table:
            return
        rows = [r for r in table if not re.match(r'^\s*\|?[\s:|-]+\|?\s*$', r)]
        if rows:
            out.append('<table>')
            for n, row in enumerate(rows):
                cells = [c.strip() for c in row.strip().strip('|').split('|')]
                tag = 'th' if n == 0 else 'td'
                out.append('<tr>' + ''.join('<' + tag + '>' + inline(c) + '</' + tag + '>'
                                            for c in cells) + '</tr>')
            out.append('</table>')
        table.clear()

    for line in text.split('\n'):
        body = line.rstrip()
        indent = len(body) - len(body.lstrip())
        stripped = body.strip()

        if CANVAS_MARK.match(stripped):
            flush_para(); close_quote()
            continue

        if stripped.startswith('\x00BLOCK'):
            flush_para(); close_lists(); close_quote(); flush_table()
            out.append(stripped)
            continue

        if stripped.startswith('|') and '|' in stripped[1:]:
            flush_para(); close_lists(); close_quote()
            table.append(stripped)
            continue
        flush_table()

        if not stripped:
            flush_para(); close_quote()
            continue

        heading = re.match(r'^(#{1,6})\s+(.*)$', stripped)
        if heading:
            flush_para(); close_lists(); close_quote()
            level = min(len(heading.group(1)) + 2, 6)
            out.append('<h' + str(level) + '>' + inline(heading.group(2)) + '</h' + str(level) + '>')
            continue

        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', stripped):
            flush_para(); close_lists(); close_quote()
            out.append('<hr>')
            continue

        if stripped.startswith('&gt;'):
            flush_para(); close_lists()
            if not in_quote:
                out.append('<blockquote>')
                in_quote = True
            out.append('<p>' + inline(stripped[4:].strip()) + '</p>')
            continue
        close_quote()

        ordered = re.match(r'^(\d+)[.)]\s+(.*)$', stripped)
        bullet = re.match(r'^[-*+]\s+(.*)$', stripped)
        if ordered or bullet:
            flush_para()
            tag = 'ol' if ordered else 'ul'
            depth = min(1 + indent // 2, 4)
            close_lists(depth)
            if len(stack) == depth and stack[-1] != tag:
                close_list()
            while len(stack) < depth:
                open_list(tag)
            close_item()
            if ordered:
                out.append('<li value="' + ordered.group(1) + '">' + inline(ordered.group(2)))
            else:
                out.append('<li>' + inline(bullet.group(1)))
            li_open[-1] = True
            continue
        if stack and indent < 2:
            flush_para()
            close_lists()

        para.append(stripped)

    flush_para(); close_lists(); close_quote(); flush_table()
    result = '\n'.join(out)
    for n, block in enumerate(blocks):
        result = result.replace('\x00BLOCK' + str(n) + '\x00', block)
    return result


TAGS = re.compile(r'<[^>]+>')


def plain_preview(fragment, limit=64):
    text = TAGS.sub(' ', fragment)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit].rstrip() + ('...' if len(text) > limit else '')


def latest_leaf(mapping):
    parents = {node.get('parent') for node in mapping.values() if node.get('parent')}
    best_id = None
    best_time = -1
    for node_id, node in mapping.items():
        if node_id in parents:
            continue
        stamp = ((node.get('message') or {}).get('create_time')) or 0
        if stamp >= best_time:
            best_time = stamp
            best_id = node_id
    return best_id


def active_path(conv):
    mapping = conv.get('mapping') or {}
    node_id = conv.get('current_node')
    if node_id not in mapping:
        node_id = latest_leaf(mapping)
    chain = []
    seen = set()
    while node_id and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        chain.append(mapping[node_id])
        node_id = mapping[node_id].get('parent')
    chain.reverse()
    return chain


def looks_like_dump(text):
    body = text.strip()
    if body.startswith('{') or body.startswith('['):
        return True
    if re.search(r'<\w+[^>]*>', body):
        return True
    return max((len(line) for line in body.split('\n')), default=0) > 1000


def service_label(msg):
    content = msg.get('content') or {}
    ctype = content.get('content_type')
    author = msg.get('author') or {}
    recipient = msg.get('recipient') or 'all'
    if ctype == 'thoughts':
        return 'reasoning'
    if ctype == 'reasoning_recap':
        return 'reasoning summary'
    if ctype == 'code':
        return 'call to ' + recipient
    if ctype == 'execution_output':
        return 'execution output'
    if ctype in ('tether_browsing_display', 'tether_quote'):
        return 'web source'
    if author.get('role') == 'tool':
        return 'reply from ' + (author.get('name') or 'tool')
    return ctype or 'tool step'


def render_message(msg, file_map, depth_prefix, stats):
    author = msg.get('author') or {}
    role = author.get('role')
    meta = msg.get('metadata') or {}
    if meta.get('is_visually_hidden_from_conversation') or role == 'system':
        return None

    content = msg.get('content') or {}
    ctype = content.get('content_type')
    recipient = msg.get('recipient') or 'all'
    parts = content.get('parts') if isinstance(content.get('parts'), list) else []
    refs = meta.get('content_references')

    def image_tag(pointer):
        fid = pointer_id(pointer)
        name = file_map.get(fid) if fid else None
        if fid:
            stats['refs'].add(fid)
            if name:
                stats['found'].add(fid)
        if not name:
            stats['missing_images'] += 1
            return '<div class="miss">Image missing from archive</div>'
        src = depth_prefix + 'files/' + quote(name)
        alt = html.escape(name.split('__', 1)[-1])
        if os.path.splitext(name)[1].lower() not in IMAGE_EXT:
            return '<div class="attach"><a href="' + src + '" target="_blank">' + alt + '</a></div>'
        stats['images'] += 1
        return ('<a href="' + src + '" target="_blank">'
                '<img loading="lazy" decoding="async" alt="' + alt + '"' + size_attrs(name)
                + ' src="' + src + '"></a>')

    has_image = False
    shown = set()
    if ctype in ('text', 'multimodal_text'):
        chunks = []
        for part in parts:
            if isinstance(part, str):
                cleaned = clean_citations(part, refs)
                if not cleaned.strip():
                    continue

                tool_name = (author.get('name') or '')
                if role == 'tool' and tool_name != 'a8km123' and looks_like_dump(cleaned):
                    chunks.append('<pre><code>' + html.escape(cleaned) + '</code></pre>')
                else:
                    chunks.append(md_to_html(cleaned))
            elif isinstance(part, dict):
                pointer = part.get('asset_pointer')
                kind = part.get('content_type')
                if kind == 'image_asset_pointer' and pointer:
                    key = pointer_id(pointer)
                    if key in shown:
                        continue
                    has_image = True
                    shown.add(key)
                    chunks.append(image_tag(pointer))
                elif kind == 'audio_transcription' and part.get('text'):
                    chunks.append(md_to_html(clean_citations(part['text'], refs)))
        body = '\n'.join(chunks)
    elif ctype == 'thoughts':
        items = []
        for th in (content.get('thoughts') or []):
            head = (th.get('summary') or '').strip()
            text = clean_citations(th.get('content') or '', refs).strip()
            if text.strip('*').strip() == head:
                text = ''
            items.append('<div class="think-item"><b>' + html.escape(head) + '</b>'
                         + md_to_html(text) + '</div>')
        body = '\n'.join(items)
    elif ctype == 'reasoning_recap':
        body = '<div class="recap">' + html.escape(content.get('content') or '') + '</div>'
    elif ctype == 'code':
        raw_code = content.get('text') or ''
        body = ('<pre><code>' + html.escape(raw_code) + '</code></pre>') if raw_code.strip() else ''
    elif ctype == 'computer_output':
        shot = (content.get('screenshot') or {}).get('asset_pointer')
        body = ''
        if shot:
            shown.add(pointer_id(shot))
            body = image_tag(shot)
        if content.get('text'):
            body += '<pre><code>' + html.escape(content['text']) + '</code></pre>'
    elif ctype == 'execution_output':
        raw_out = (content.get('text') or '').replace('<<ImageDisplayed>>', '').strip()
        body = ('<pre><code>' + html.escape(raw_out) + '</code></pre>') if raw_out else ''
        for produced in ((meta.get('aggregate_result') or {}).get('messages') or []):
            if produced.get('message_type') == 'image' and produced.get('image_url'):
                shown.add(pointer_id(produced['image_url']))
                body += image_tag(produced['image_url'])
    elif ctype in ('tether_browsing_display', 'tether_quote'):
        raw = clean_citations(content.get('result') or content.get('text') or '', refs).strip()
        body = ('<pre><code>' + html.escape(raw[:20000]) + '</code></pre>') if raw else ''
    else:
        body = '<pre><code>' + html.escape(json.dumps(content, ensure_ascii=False)[:8000]) + '</code></pre>'

    if not body.strip():
        found = []
        for group in (meta.get('search_result_groups') or []):
            for item in (group.get('entries') or []):
                title = html.escape(item.get('title') or item.get('url') or '')
                url = item.get('url') or ''
                snippet = html.escape(re.sub(r'[*`_]{1,2}', '', (item.get('snippet') or ''))[:300])
                if url.startswith('http'):
                    found.append('<li><a href="' + html.escape(url, quote=True)
                                 + '" target="_blank" rel="noreferrer">' + title + '</a>'
                                 + ('<br>' + snippet if snippet else '') + '</li>')
                elif title:
                    found.append('<li>' + title + '</li>')
        if found:
            body = '<ul>' + ''.join(found) + '</ul>'

    attach = meta.get('attachments') or []
    if attach:
        links = []
        for a in attach:
            if a.get('id') in shown:
                continue
            name = file_map.get(a.get('id'))
            if a.get('id'):
                stats['refs'].add(a['id'])
                if name:
                    stats['found'].add(a['id'])
            raw_label = a.get('name') or a.get('id') or 'file'
            label = html.escape(os.path.basename(raw_label.replace(chr(92), '/')))
            if not name:
                links.append('<span class="miss">' + label + ' (missing)</span>')
                continue

            if os.path.splitext(name)[1].lower() in IMAGE_EXT:
                has_image = True
                stats['images'] += 1
                src_path = depth_prefix + 'files/' + quote(name)
                body += ('<a href="' + src_path + '" target="_blank">'
                         '<img loading="lazy" decoding="async" alt="' + label + '"' + size_attrs(name)
                         + ' src="' + src_path + '"></a>')
                continue
            links.append('<a href="' + depth_prefix + 'files/' + quote(name)
                         + '" target="_blank">' + label + '</a>')
        if links:
            body += '<div class="attach">Attachments: ' + ', '.join(links) + '</div>'

    if not body.strip():
        return None

    tool_output = ctype in ('execution_output', 'computer_output')
    is_main = (not tool_output) and (has_image or (role == 'user') or (
        role == 'assistant' and recipient == 'all' and ctype in ('text', 'multimodal_text')))

    if is_main:
        stats['shown'] += 1
        cls = 'msg user' if role == 'user' else 'msg bot'
        who = 'You' if role == 'user' else 'ChatGPT'
        return ('main', who,
                '<div class="' + cls + '"><div class="who">' + who
                + '</div><div class="body">' + body + '</div></div>')

    label = service_label(msg)
    return ('service', label,
            '<div class="svc-item"><div class="svc-who">' + html.escape(label) + '</div>' + body + '</div>')


def actions_html():
    return ('<div class="seg" role="group" aria-label="Column width">'
            '<button type="button" data-w="narrow">Narrow</button>'
            '<button type="button" data-w="normal">Normal</button>'
            '<button type="button" data-w="wide">Wide</button></div>'
            '<button id="theme" class="icon" type="button" '
            'aria-label="Toggle theme" title="Toggle theme">'
            '<svg class="ic sun" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.6v2.2M12 19.2v2.2M4.2 12H2M22 12h-2.2M5.9 5.9 4.4 4.4M19.6 19.6l-1.5-1.5M18.1 5.9l1.5-1.5M4.4 19.6l1.5-1.5"/></svg>'
            '<svg class="ic moon" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 14.6A8.6 8.6 0 0 1 9.4 3.5a8.6 8.6 0 1 0 11.1 11.1z"/></svg>'
            '</button>')


def badge_html(source):
    return '<span class="badge">archived</span>' if source == 'archived' else ''


def volume_html(entry):
    pics = ''
    if entry['i']:
        label = str(entry['i']) + ' ' + plural(entry['i'], ('image', 'images'))
        pics = ('<span class="vol pics" role="img" aria-label="' + label + '" title="' + label + '">'
                + ICON_PIC + '<span class="n">' + str(entry['i']) + '</span></span>')
    count = str(entry['m']) + ' ' + plural(entry['m'], ('message', 'messages'))
    msgs = ('<span class="vol msgs" role="img" aria-label="' + count + '" title="' + count + '">'
            + ICON_MSG + '<span class="n">' + str(entry['m']) + '</span></span>')
    return '<span class="vols">' + pics + msgs + '</span>'


def seo_tags(title, rel_url):
    if not SEO_BASE:
        return ''
    page_url = SEO_BASE + rel_url
    return ('<meta name="description" content="' + html.escape(SEO_DESCRIPTION, True) + '">'
            '<link rel="canonical" href="' + html.escape(page_url, True) + '">'
            '<meta property="og:type" content="website">'
            '<meta property="og:site_name" content="ChatGPT Export Viewer">'
            '<meta property="og:title" content="' + html.escape(title, True) + '">'
            '<meta property="og:description" content="' + html.escape(SEO_DESCRIPTION, True) + '">'
            '<meta property="og:url" content="' + html.escape(page_url, True) + '">'
            '<meta property="og:image" content="' + html.escape(SEO_BASE + 'og.png', True) + '">'
            '<meta name="twitter:card" content="summary_large_image">')


def head_tags(depth_prefix, with_math):
    site = depth_prefix + 'site/'
    tags = ('<meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<script>(function(){var t=localStorage.getItem("theme");'
            'if(!t){t=window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";}'
            'document.documentElement.setAttribute("data-theme",t);'
            'var w=localStorage.getItem("width")||"normal";'
            'document.documentElement.setAttribute("data-width",w);})();</script>'

            '<style>html[data-theme="dark"]{background:#0d1117;color-scheme:dark}'
            'html[data-theme="light"]{background:#fff;color-scheme:light}</style>'
            '<link rel="stylesheet" href="' + site + 'assets/style.css">')
    if with_math:
        tags += '<link rel="stylesheet" href="' + site + 'assets/katex/katex.min.css">'
    return tags


def foot_tags(depth_prefix, with_math, extra):
    site = depth_prefix + 'site/'
    tags = '<script src="' + site + 'assets/theme.js"></script>'
    if with_math:
        tags += ('<script src="' + site + 'assets/katex/katex.min.js"></script>'
                 '<script src="' + site + 'assets/katex/auto-render.min.js"></script>')
    return tags + extra


def main():
    global SITE, FILES, SEO_BASE
    argv = sys.argv[1:]
    if '--seo' in argv:
        at = argv.index('--seo')
        if at + 1 >= len(argv) or argv[at + 1].startswith('-'):
            print('--seo requires the public base URL of the site')
            return 1
        SEO_BASE = argv[at + 1].rstrip('/') + '/'
        del argv[at:at + 2]

    if not argv:
        print('Usage: python3 build_site.py <export.zip|export-dir> [output-dir] [--seo <base-url>]')
        return 1

    source = os.path.abspath(argv[0])
    if not os.path.exists(source):
        print('Source not found:', source)
        return 1
    out_base = (os.path.abspath(argv[1]) if len(argv) > 1
                else os.path.splitext(source)[0] + '-site')
    SITE = os.path.join(out_base, 'site')
    FILES = os.path.join(out_base, 'files')

    if os.path.isfile(source) and not zipfile.is_zipfile(source):
        print('Not a ZIP archive:', source)
        return 1

    names, opener, root = export_reader(source)
    shards = shard_names(names, opener)
    if not shards:
        print('No conversations.json found in', source)
        return 1

    try:
        os.makedirs(SITE, exist_ok=True)
    except OSError as err:
        print('Cannot write to', out_base + ':', err.strerror)
        return 1

    print('source:', os.path.basename(source), '|', len(shards), 'conversation file(s)')
    file_map = extract_assets(names, opener, FILES, root)
    print('assets extracted:', len(file_map), 'to', FILES)

    shutil.rmtree(os.path.join(SITE, 'chats'), ignore_errors=True)
    os.makedirs(os.path.join(SITE, 'assets'), exist_ok=True)

    entries = []
    missing_by_chat = []
    made_dirs = set()
    stats = {'images': 0, 'missing_images': 0, 'shown': 0, 'refs': set(), 'found': set()}

    for n, conv in enumerate(iter_conversations(names, opener), 1):
        if n % 300 == 0:
            print('processed', n)
        cid = conv.get('conversation_id') or conv.get('id') or ''

        ts = conv.get('update_time') or conv.get('create_time') or 0
        raw_date = (datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%Y-%m-%d')
                    if ts else '0000-00-00')
        year, month = raw_date[:4], raw_date[5:7]

        title = conv.get('title') or 'Untitled'
        rel_dir = os.path.join('chats', year, month)

        if rel_dir not in made_dirs:
            os.makedirs(os.path.join(SITE, rel_dir), exist_ok=True)
            made_dirs.add(rel_dir)
        fname = raw_date + '-' + slugify(title) + '-' + cid[:8] + '.html'
        depth_prefix = '../../../../'

        images_before = stats['images']
        shown_before = stats['shown']
        lost_before = len(stats['refs']) - len(stats['found'])
        rendered = []
        user_text = []
        pending = []
        service_total = 0


        def flush_service():
            nonlocal service_total
            if not pending:
                return
            counts = Counter(label for label, _ in pending)
            summary = ', '.join(k + (' x' + str(v) if v > 1 else '') for k, v in counts.items())
            service_total += len(pending)
            rendered.append('<details class="svc"><summary>Tool steps: ' + str(len(pending))
                            + ' (' + html.escape(summary) + ')</summary><div class="svc-body">'
                            + ''.join(body for _, body in pending) + '</div></details>')
            pending.clear()

        asks = []
        for node in active_path(conv):
            msg = node.get('message')
            if not msg:
                continue
            piece = render_message(msg, file_map, depth_prefix, stats)
            if piece:
                kind, label, body = piece
                if kind == 'service':
                    pending.append((label, body))
                else:
                    flush_service()
                    if label == 'You':
                        mark = 'ask' + str(len(asks) + 1)
                        body = body.replace('<div class="msg user"',
                                            '<div class="msg user" id="' + mark + '"', 1)
                        inner = body.split('<div class="body">', 1)[-1]
                        preview = plain_preview(inner)
                        if not preview or preview.startswith('Image missing from archive'):
                            preview = 'image' if ('<img' in inner or 'miss' in inner) else 'attachment'
                        asks.append((mark, preview))
                    rendered.append(body)
            role = (msg.get('author') or {}).get('role')
            if piece and piece[0] == 'main' and role in ('user', 'assistant'):
                for p in (msg.get('content') or {}).get('parts') or []:
                    if isinstance(p, str) and p.strip():
                        user_text.append(clean_citations(p, (msg.get('metadata') or {}).get('content_references')))
        flush_service()

        origin = 'archived' if conv.get('is_archived') else 'main'
        badge = badge_html(origin)

        body_html = '\n'.join(rendered)

        head = ('<header class="chat-head"><div class="wrap">'
                '<div class="head-row"><h1 title="' + html.escape(title) + '">'
                + html.escape(title) + '</h1><div class="actions">'
                + ('<button id="toggle" type="button">Tool steps</button>' if service_total else '')
                + actions_html() + '</div></div>'
                '<div class="sub">'
                + '<a class="back" href="' + depth_prefix + 'site/index.html">Back to list</a>'
                + '<span>' + raw_date + '</span>' + badge
                + '</div></div></header>')

        with_math = 'math-block' in body_html or 'math-inline' in body_html


        rail = ''
        if len(asks) >= 3:
            items = ''.join('<a href="#' + mark + '">' + str(n + 1) + '. ' + html.escape(preview) + '</a>'
                            for n, (mark, preview) in enumerate(asks))
            rail = ('<aside class="rail"><div class="rail-head">Questions: '
                    + str(len(asks)) + '</div>' + items + '</aside>')

        page = ('<!doctype html><html lang="en"><head>' + head_tags(depth_prefix, with_math)
                + '<title>' + html.escape(title) + '</title>'
                + seo_tags(title, 'site/chats/' + year + '/' + month + '/' + fname) + '</head>'
                '<body><div class="page">' + head
                + '<div class="chat-layout">'
                + '<main class="chat">' + body_html + '</main>' + rail + '</div></div>'
                + foot_tags(depth_prefix, with_math,
                            '<script src="' + depth_prefix + 'site/assets/chat.js"></script>')
                + '</body></html>')
        with open(os.path.join(SITE, rel_dir, fname), 'w', encoding='utf-8') as fh:
            fh.write(page)

        entries.append({
            'i': stats['images'] - images_before,
            't': title,
            'd': raw_date,
            'u': 'chats/' + year + '/' + month + '/' + fname,
            'm': stats['shown'] - shown_before,
            's': origin,
            'q': re.sub(r'\s+', ' ', ' '.join(user_text))[:TEXT_LIMIT],
        })

        lost_here = len(stats['refs']) - len(stats['found']) - lost_before
        if lost_here:
            missing_by_chat.append((lost_here, raw_date, title))

    entries.sort(key=lambda e: (e['d'], e['t']), reverse=True)

    corpus = [entry.pop('q') for entry in entries]
    with open(os.path.join(SITE, 'search-index.js'), 'w', encoding='utf-8') as fh:
        fh.write('var CHATS = ' + json.dumps(entries, ensure_ascii=False, separators=(',', ':')) + ';')
    packed = json.dumps(corpus, ensure_ascii=False, separators=(',', ':'))
    with open(os.path.join(SITE, 'search-text.js'), 'w', encoding='utf-8') as fh:
        fh.write('var CHAT_TEXT = JSON.parse(' + json.dumps(packed, ensure_ascii=False) + ');')

    years = {}
    for e in entries:
        years.setdefault(e['d'][:4], {}).setdefault(e['d'][5:7], []).append(e)


    parts = ['<div class="page"><header class="top"><div class="wrap">'
             + '<div class="head-row"><h1>ChatGPT Archive</h1>'
             + '<div class="actions">' + actions_html() + '</div></div>'
             + '<div class="sub">'
             + '<span>' + str(len(entries)) + ' '
             + plural(len(entries), ('conversation', 'conversations')) + '</span>'
             + '<span>' + str(stats['shown']) + ' '
             + plural(stats['shown'], ('message', 'messages')) + '</span>'
             + '<span>' + str(stats['images']) + ' '
             + plural(stats['images'], ('image', 'images'))
             + '</span>'

             + ('<span class="warn" title="Referenced in conversations but missing from the archive">'
                + str(len(stats['refs'] - stats['found'])) + ' of '
                + str(len(stats['refs'])) + ' ' + plural(len(stats['refs']), ('file', 'files'))
                + ' missing'
                + '</span>' if stats['refs'] - stats['found'] else '')
             + '</div>'
             + '</div></header><div class="chat-layout"><main id="list">'
             + '<div class="search">'
             + '<input id="q" type="search" aria-label="Search the archive"'
             + ' placeholder="Search titles and your messages" autocomplete="off">'
             + '<div id="found" class="stat" role="status"></div></div><div id="months">']
    for year in sorted(years, reverse=True):
        parts.append('<section class="year"><h2 id="y' + year + '">' + year + '</h2>')
        for month in sorted(years[year], reverse=True):
            rows = years[year][month]

            parts.append('<section class="month" id="m' + year + '-' + month + '"'
                         + ' style="contain-intrinsic-size:auto ' + str(41 + 43 * len(rows)) + 'px">'
                         + '<h3>' + MONTHS[int(month)]
                         + ' <span class="cnt">' + str(len(rows)) + '</span></h3><ul>')
            for e in rows:
                parts.append('<li><a href="' + quote(e['u']) + '">' + html.escape(e['t']) + '</a>'
                             + badge_html(e['s']) + volume_html(e)
                             + '<span class="date">' + e['d'] + '</span></li>')
            parts.append('</ul></section>')
        parts.append('</section>')


    rail = ['<aside class="rail"><div class="rail-head">Conversations: ' + str(len(entries)) + '</div>']
    for year in sorted(years, reverse=True):
        rail.append('<div class="rail-year">' + year + '</div>')
        for month in sorted(years[year], reverse=True):
            rail.append('<a href="#m' + year + '-' + month + '">' + MONTHS[int(month)]
                        + '<span class="num">' + str(len(years[year][month])) + '</span></a>')
    rail.append('</aside>')

    parts.append('</div><div id="results"></div></main>' + ''.join(rail) + '</div></div>'
                 '<script src="assets/theme.js"></script>'

                 '<script defer src="search-index.js"></script>'
                 '<script defer src="assets/app.js"></script>')

    with open(os.path.join(SITE, 'index.html'), 'w', encoding='utf-8') as fh:
        index_title = ('ChatGPT Export Viewer: read your ChatGPT export offline'
                       if SEO_BASE else 'ChatGPT Archive')
        fh.write('<!doctype html><html lang="en"><head>' + head_tags('../', False)
                 + '<title>' + html.escape(index_title) + '</title>'
                 + seo_tags(index_title, 'site/index.html') + '</head><body>'
                 + ''.join(parts) + '</body></html>')

    write_assets()
    print('---')
    print('conversations:', len(entries))
    print('messages:', stats['shown'])
    print('images shown:', stats['images'], '| missing:', stats['missing_images'])
    lost = stats['refs'] - stats['found']
    print('files referenced:', len(stats['refs']), '| resolved:', len(stats['found']),
          '| missing:', len(lost))
    if lost:
        report = os.path.join(out_base, 'missing-files.txt')
        with open(report, 'w', encoding='utf-8') as fh:
            fh.write('Files referenced in conversations but missing from the archive\n')
            fh.write('Referenced: ' + str(len(stats['refs'])) + '\n')
            fh.write('Resolved: ' + str(len(stats['found'])) + '\n')
            fh.write('Missing: ' + str(len(lost)) + '\n\n')
            for row in sorted(missing_by_chat, key=lambda item: -item[0]):
                fh.write(str(row[0]) + '\t' + row[1] + '\t' + row[2] + '\n')
            fh.write('\n')
            for fid in sorted(lost):
                fh.write(fid + '\n')
        print('missing files report:', report)
    print('site:', os.path.join(SITE, 'index.html'))
    return 0


def write_assets():
    css = """
:root[data-theme="dark"] {
  --canvas:#0d1117; --subtle:#161b22; --inset:#010409;
  --border:#30363d; --border-soft:#21262d;
  --fg:#e6edf3; --muted:#9198a1; --faint:#7b848f; --warn:#d29922;
  --accent:#4493f8; --chip:#1f6feb26; --mark-bg:#bb800940; --mark-fg:#f2cc60;
  --skeleton:#1c2331;
}
:root[data-theme="light"] {
  --canvas:#ffffff; --subtle:#f6f8fa; --inset:#f6f8fa;
  --border:#d1d9e0; --border-soft:#d8dee4;
  --fg:#1f2328; --muted:#59636e; --faint:#68717f; --warn:#956c18;
  --accent:#0969da; --chip:#ddf4ff; --mark-bg:#fff8c5; --mark-fg:#4d2d00;
  --skeleton:#eaeef2;
}
* { box-sizing:border-box; }
html { -webkit-text-size-adjust:100%; scrollbar-gutter:stable; }
body {
  margin:0; background:var(--canvas); color:var(--fg);
  font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;
}
:root {
  --wrap:1060px; --rail-w:236px; --rail-gap:40px; --pad-x:28px; --radius:6px;
  --bleed:20px; --col-pad:24px;
  --head-h:92px;
  --shell:calc(var(--wrap) + var(--rail-w) + var(--rail-gap));
}
:root[data-width="narrow"] { --wrap:820px; }
:root[data-width="wide"] { --wrap:1340px; }
.wrap { width:100%; max-width:var(--shell); margin:0 auto; padding:0 var(--pad-x); }
[id] { scroll-margin-top:calc(var(--head-h) + 16px); }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }

.top, .chat-head {
  position:sticky; top:0; z-index:5; padding:16px 0 14px;
  background:var(--canvas); border-bottom:1px solid var(--border); 
}
h1 { margin:0 0 4px; font-size:24px; line-height:1.3; font-weight:600;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.sub, .stat { color:var(--muted); font-size:13px; }
.sub { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-top:4px; }
.back { color:var(--muted); }
button {
  padding:4px 11px; font:inherit; font-size:12px; cursor:pointer;
  background:var(--subtle); color:var(--muted);
  border:1px solid var(--border); border-radius:var(--radius);
}
button:hover { color:var(--fg); border-color:var(--faint); }

.seg { display:inline-flex; border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; background:var(--subtle); }
.seg button { border:0; border-radius:0; background:none; padding:4px 11px; }
.seg button + button { border-left:1px solid var(--border); }
.seg button.on { background:var(--chip); color:var(--fg); }
.seg button:hover { color:var(--fg); }

button.icon { display:inline-flex; align-items:center; justify-content:center; width:32px; padding:0; }
button.icon .ic { display:none; }
:root[data-theme="dark"] button.icon .sun { display:block; }
:root[data-theme="light"] button.icon .moon { display:block; }

* { scrollbar-width:thin; scrollbar-color:var(--border) transparent; }
::-webkit-scrollbar { width:10px; height:10px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:var(--border); border-radius:8px; border:2px solid var(--canvas); }
::-webkit-scrollbar-thumb:hover { background:var(--faint); }
.head-row { display:flex; align-items:center; gap:12px; }
.head-row h1 { flex:1; min-width:0; }
.actions { display:flex; gap:8px; flex-shrink:0; align-items:stretch; }
#q {
  width:100%; padding:8px 12px; border-radius:var(--radius);
  border:1px solid var(--border); background:var(--canvas); color:var(--fg); font:inherit;
}
#q:focus { outline:none; border-color:var(--accent); box-shadow:0 0 0 3px var(--chip); }

main { padding-bottom:80px; }
h2 { margin:32px 0 2px; font-size:20px; font-weight:600; }
h3 { margin:20px 0 2px; font-size:12px; color:var(--faint); font-weight:600;
     text-transform:uppercase; letter-spacing:.05em; }
#months > section.year:first-child > h2 { margin-top:0; }
.month { content-visibility:auto; }
#list ul { list-style:none; margin:0; padding:0; }
#list li { padding:8px 0; border-bottom:1px solid var(--border-soft); display:flex; gap:12px; align-items:baseline; }
#list li a { flex:1; overflow-wrap:anywhere; }
.vols { display:grid; grid-template-columns:41px 41px; gap:14px; margin-left:auto; margin-right:16px; }
.vols .pics { grid-column:1; }
.vols .msgs { grid-column:2; }
.vol { display:grid; grid-template-columns:13px 24px; gap:4px; align-items:center;
  color:var(--faint); font-size:12px; font-variant-numeric:tabular-nums; }
.vol .n { text-align:left; }
.vol svg { opacity:.8; }
.hit .vols { display:inline-grid; margin-left:16px; margin-right:0; vertical-align:middle; }
.hit .date { margin-left:16px; }
.date { color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; white-space:nowrap; }
.cnt { color:var(--faint); font-weight:400; }
.badge { background:var(--chip); color:var(--accent); border-radius:12px; padding:1px 9px; font-size:11px; white-space:nowrap; }

.chat-layout {
  display:grid; grid-template-columns:minmax(0,1fr) var(--rail-w); gap:var(--rail-gap);
  align-items:start; width:100%; max-width:var(--shell); margin:0 auto; padding:0 var(--pad-x);
}
.chat-layout > main { max-width:none; margin:0; padding:var(--col-pad) 0 80px; }
.search { position:sticky; top:var(--head-h); z-index:4; background:var(--canvas);
  margin-top:calc(var(--col-pad) * -1); padding:var(--col-pad) 0 12px; }

.rail { position:sticky; top:var(--head-h); max-height:calc(100vh - var(--head-h));
  overflow:auto; padding:24px 0 20px; }
.rail-head { font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--faint); margin-bottom:10px; padding-left:11px; }
.rail-year { font-size:13px; font-weight:600; color:var(--fg); margin:14px 0 4px; padding-left:11px; }
.rail-head + .rail-year { margin-top:0; }
.rail a {
  display:flex; gap:8px; justify-content:space-between; padding:6px 10px; margin-bottom:1px;
  border-radius:0 var(--radius) var(--radius) 0;
  border-left:2px solid transparent; color:var(--faint); font-size:12.5px; line-height:1.45;
}
.rail a:hover { color:var(--fg); background:var(--subtle); text-decoration:none; }
.rail a.on { color:var(--fg); background:var(--subtle); border-left-color:var(--accent); }
.rail .num { color:var(--faint); font-variant-numeric:tabular-nums; flex-shrink:0; }

.msg { margin:0 0 24px; }
.msg.user {
  background:var(--subtle);
  border-top:1px solid var(--border-soft); border-bottom:1px solid var(--border-soft);
  margin:0 calc(var(--bleed) * -1) 26px; padding:16px var(--bleed);
}
.msg.bot { margin:0 calc(var(--bleed) * -1) 26px; padding:0 var(--bleed) 26px;
  border-bottom:1px solid var(--border-soft); }
.who { font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--faint); margin-bottom:10px; }

.body { overflow-wrap:anywhere; }
.body > :first-child { margin-top:0; }
.body > :last-child { margin-bottom:0; }
.body p { margin:0 0 14px; }
.body h3, .body h4, .body h5 {
  margin:26px 0 12px; color:var(--fg); text-transform:none; letter-spacing:0; font-weight:600;
}
.body h3 { font-size:19px; padding-bottom:6px; border-bottom:1px solid var(--border-soft); }
.body h4 { font-size:16.5px; } .body h5 { font-size:15px; }
.body h6 { font-size:14px; color:var(--muted); margin:18px 0 8px; font-weight:600;
  text-transform:none; letter-spacing:0; }
.nolink { color:var(--muted); border-bottom:1px dotted var(--border); cursor:help; }
.body details { border:1px solid var(--border); border-radius:var(--radius); padding:8px 14px; margin:0 0 14px; }
.body details summary { cursor:pointer; color:var(--muted); font-size:14px; }
.body ul, .body ol { margin:0 0 14px; padding-left:26px; }
.body li { margin:4px 0; }
.body li > ul, .body li > ol { margin:4px 0; }
.body hr { border:0; border-top:1px solid var(--border); margin:22px 0; }
blockquote { border-left:3px solid var(--border); margin:0 0 14px; padding:0 16px; color:var(--muted); }
pre {
  background:var(--subtle); border:1px solid var(--border-soft); border-radius:var(--radius);
  padding:14px 16px; overflow:auto; margin:0 0 14px; line-height:1.45;
}
code { font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace; font-size:13px; }
p code, li code, td code, h3 code, h4 code { background:var(--chip); padding:2px 6px; border-radius:var(--radius); font-size:12.5px; }
img {
  max-width:100%; width:var(--iw, auto); height:auto; display:block;
  margin:10px 0; border:1px solid var(--border); border-radius:var(--radius); cursor:zoom-in;
  background:var(--skeleton);
}
img.ready { background:none; }
table { border-collapse:collapse; margin:0 0 14px; width:100%; font-size:14px; display:block; overflow-x:auto; }
th, td { border:1px solid var(--border); padding:6px 13px; text-align:left; vertical-align:top; }
th { background:var(--subtle); font-weight:600; }

.math-block { display:block; margin:16px 0; overflow-x:auto; }
.katex { font-size:1.02em; }
.katex-display { margin:0; }

details.svc { margin:0 calc(var(--bleed) * -1) 20px; border-left:2px solid var(--border);
  padding:2px 0 2px 18px; }
details.svc > summary { cursor:pointer; color:var(--faint); font-size:13px; list-style:none; padding:2px 0; }
details.svc > summary::-webkit-details-marker { display:none; }
details.svc > summary::before { content:"▸"; margin-right:6px; }
details.svc[open] > summary::before { content:"▾"; margin-right:6px; }
details.svc > summary:hover { color:var(--muted); }
.svc-body { margin-top:10px; }
.svc-item { margin:0 0 14px; overflow-wrap:anywhere; }
.svc-item p { margin:0 0 14px; }
.svc-item ul, .svc-item ol { margin:0 0 14px; padding-left:26px; }
.svc-item h3, .svc-item h4, .svc-item h5, .svc-item h6 {
  font-size:14px; color:var(--muted); font-weight:600; margin:14px 0 8px;
  text-transform:none; letter-spacing:0; border:0; padding:0;
}
.svc-who { font-size:11px; letter-spacing:.05em; text-transform:uppercase; color:var(--faint); margin-bottom:6px; }
.svc-item pre { font-size:12px; max-height:400px; }
.svc-item img { width:auto; max-height:240px; }
.recap { color:var(--faint); font-size:13px; font-style:italic; }
.think-item { margin:0 0 12px; font-size:14.5px; color:var(--muted); }
.think-item b { color:var(--fg); display:block; margin-bottom:4px; font-weight:600; }
.attach { margin-top:12px; font-size:13px; color:var(--muted); }
.miss { color:var(--warn); font-size:13px; }
.warn { color:var(--warn); }

.lb {
  position:fixed; inset:0; z-index:50; background:rgba(1,4,9,.92);
  display:flex; align-items:center; justify-content:center; padding:64px 24px 24px;
}
.lb[hidden] { display:none; }
.lb-img { width:auto; max-width:100%; max-height:100%; border-radius:var(--radius);
  border:1px solid var(--border); cursor:default; margin:0; }
.lb-bar {
  position:absolute; top:0; left:0; right:0; height:52px; display:flex; align-items:center;
  gap:10px; padding:0 18px; background:rgba(1,4,9,.7); backdrop-filter:blur(6px);
}
.lb-count { color:#9198a1; font-size:13px; font-variant-numeric:tabular-nums; }
.lb-bar .sp { flex:1; }
.lb-nav {
  position:absolute; top:50%; transform:translateY(-50%); width:44px; height:64px;
  font-size:26px; line-height:1; padding:0; background:rgba(22,27,34,.8); color:#e6edf3;
}
.lb-prev { left:14px; } .lb-next { right:14px; }
.hit { padding:10px 0; border-bottom:1px solid var(--border-soft); }
.ctx { color:var(--muted); font-size:13px; margin-top:4px; }
mark { background:var(--mark-bg); color:var(--mark-fg); border-radius:3px; padding:0 2px; }

@media (max-width:1095px) {
  :root[data-width="narrow"] .chat-layout { display:block; max-width:var(--wrap); }
  :root[data-width="narrow"] .wrap { max-width:var(--wrap); }
  :root[data-width="narrow"] .rail { display:none; }
}
@media (max-width:1335px) {
  :root[data-width="normal"] .chat-layout, :root:not([data-width]) .chat-layout {
    display:block; max-width:var(--wrap); }
  :root[data-width="normal"] .wrap, :root:not([data-width]) .wrap { max-width:var(--wrap); }
  :root[data-width="normal"] .rail, :root:not([data-width]) .rail { display:none; }
}
@media (max-width:1615px) {
  :root[data-width="wide"] .chat-layout { display:block; max-width:var(--wrap); }
  :root[data-width="wide"] .wrap { max-width:var(--wrap); }
  :root[data-width="wide"] .rail { display:none; }
}
@media (max-width:720px) {
  :root { --pad-x:16px; --bleed:16px; }
  h1 { font-size:20px; }
  #list li { flex-wrap:wrap; gap:4px; }
  img { width:auto; max-height:320px; }
}
"""
    theme = """
(function () {
  var root = document.documentElement;

  var themeBtn = document.getElementById('theme');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (err) {}
    });
  }

  var seg = document.querySelectorAll('.seg button[data-w]');
  if (seg.length) {
    var markWidth = function () {
      var now = root.getAttribute('data-width') || 'normal';
      for (var i = 0; i < seg.length; i++) {
        var on = seg[i].getAttribute('data-w') === now;
        seg[i].classList.toggle('on', on);
        seg[i].setAttribute('aria-pressed', on ? 'true' : 'false');
      }
    };
    for (var i = 0; i < seg.length; i++) {
      seg[i].addEventListener('click', function () {
        var pick = this.getAttribute('data-w');
        root.setAttribute('data-width', pick);
        try { localStorage.setItem('width', pick); } catch (err) {}
        markWidth();
      });
    }
    markWidth();
  }

  var head = document.querySelector('.top, .chat-head');
  if (head) {
    var measure = function () {
      root.style.setProperty('--head-h', Math.floor(head.getBoundingClientRect().height) + 'px');
    };
    measure();
    if (window.ResizeObserver) { new ResizeObserver(measure).observe(head); }
    else { window.addEventListener('resize', measure); }
  }

  var links = document.querySelectorAll('.rail a[href^="#"]');
  if (links.length) {
    var spots = [];
    for (var n = 0; n < links.length; n++) {
      var target = document.getElementById(links[n].getAttribute('href').slice(1));
      if (target) spots.push({ node: target, link: links[n] });
    }
    var tops = [];
    var current = -1;
    var queued = false;

    var measureTops = function () {
      var base = window.pageYOffset;
      tops = [];
      for (var t = 0; t < spots.length; t++) {
        tops.push(spots[t].node.getBoundingClientRect().top + base);
      }
      current = -1;
      markRail();
    };

    var markRail = function () {
      queued = false;
      if (!tops.length) return;
      var line = window.pageYOffset + (parseInt(root.style.getPropertyValue('--head-h'), 10) || 0) + 24;
      var found = 0;
      for (var f = 0; f < tops.length; f++) {
        if (tops[f] <= line) found = f;
      }
      if (found === current) return;
      current = found;
      for (var k = 0; k < spots.length; k++) {
        var on = k === found;
        spots[k].link.classList.toggle('on', on);
        if (!on) { spots[k].link.removeAttribute('aria-current'); continue; }
        spots[k].link.setAttribute('aria-current', 'true');
        var view = spots[k].link.parentNode.getBoundingClientRect();
        var item = spots[k].link.getBoundingClientRect();
        if (item.top < view.top || item.bottom > view.bottom) {
          spots[k].link.scrollIntoView({ block: 'nearest' });
        }
      }
    };

    var schedule = function () {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(markRail);
    };
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', measureTops);
    window.addEventListener('load', measureTops);
    if (window.ResizeObserver) { new ResizeObserver(measureTops).observe(document.body); }
    measureTops();
  }
})();
"""
    chat = r"""
var btn = document.getElementById('toggle');
if (btn) {
  btn.setAttribute('aria-expanded', 'false');
  btn.addEventListener('click', function () {
    var opened = btn.getAttribute('data-open') === '1';
    var blocks = document.querySelectorAll('details.svc');
    for (var i = 0; i < blocks.length; i++) { blocks[i].open = !opened; }
    btn.setAttribute('data-open', opened ? '0' : '1');
    btn.setAttribute('aria-expanded', opened ? 'false' : 'true');
    btn.textContent = opened ? 'Tool steps' : 'Collapse tool steps';
  });
}

if (window.renderMathInElement) {
  window.renderMathInElement(document.querySelector('main.chat'), {
    delimiters: [
      { left: '\\[', right: '\\]', display: true },
      { left: '\\(', right: '\\)', display: false }
    ],
    ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
    ignoredClasses: ['svc-item'],
    throwOnError: false,
    strict: false
  });
}

(function () {
  var pics = document.querySelectorAll('main.chat img');
  for (var i = 0; i < pics.length; i++) {
    if (pics[i].complete && pics[i].naturalWidth) {
      pics[i].classList.add('ready');
    } else {
      pics[i].addEventListener('load', function () { this.classList.add('ready'); });
    }
  }
})();

(function () {
  var shots = [].slice.call(document.querySelectorAll('main.chat a > img'));
  if (!shots.length) return;

  function make(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  var box = make('div', 'lb');
  box.hidden = true;
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-modal', 'true');
  box.setAttribute('aria-label', 'Image viewer');
  var bar = make('div', 'lb-bar');
  var count = make('span', 'lb-count');
  var spacer = make('span', 'sp');
  var openTab = make('button', null, 'Open in new tab');
  var closeBtn = make('button', null, 'Close');
  var prev = make('button', 'lb-nav lb-prev', '‹');
  var next = make('button', 'lb-nav lb-next', '›');
  prev.setAttribute('aria-label', 'Previous image');
  next.setAttribute('aria-label', 'Next image');
  var view = make('img', 'lb-img');
  bar.appendChild(count);
  bar.appendChild(spacer);
  bar.appendChild(openTab);
  bar.appendChild(closeBtn);
  box.appendChild(bar);
  box.appendChild(prev);
  box.appendChild(view);
  box.appendChild(next);
  document.body.appendChild(box);

  var at = 0;
  var gallery = shots;
  var cameFrom = null;
  function show(index) {
    at = (index + gallery.length) % gallery.length;
    view.src = gallery[at].src;
    view.alt = gallery[at].alt || '';
    count.textContent = (at + 1) + ' of ' + gallery.length;
    prev.hidden = gallery.length < 2;
    next.hidden = gallery.length < 2;
  }
  function open(img) {
    gallery = shots.filter(function (shot) { return shot.offsetParent !== null; });
    if (gallery.indexOf(img) < 0) { gallery = shots; }
    cameFrom = img.parentNode;
    show(gallery.indexOf(img));
    box.hidden = false;
    document.documentElement.style.overflow = 'hidden';
    closeBtn.focus();
  }
  function close() {
    box.hidden = true;
    view.removeAttribute('src');
    document.documentElement.style.overflow = '';
    if (cameFrom && cameFrom.focus) { cameFrom.focus(); }
  }

  for (var i = 0; i < shots.length; i++) {
    (function (shot) {
      shot.parentNode.addEventListener('click', function (event) {
        event.preventDefault();
        open(shot);
      });
    })(shots[i]);
  }

  prev.addEventListener('click', function (e) { e.stopPropagation(); show(at - 1); });
  next.addEventListener('click', function (e) { e.stopPropagation(); show(at + 1); });
  closeBtn.addEventListener('click', close);
  openTab.addEventListener('click', function () { window.open(gallery[at].src, '_blank', 'noopener'); });
  box.addEventListener('click', function (event) {
    if (event.target === box) close();
  });
  document.addEventListener('keydown', function (event) {
    if (box.hidden) return;
    if (event.key === 'Escape') close();
    if (event.key === 'ArrowLeft') show(at - 1);
    if (event.key === 'ArrowRight') show(at + 1);
  });
})();
"""
    app = """
var box = document.getElementById('q');
var months = document.getElementById('months');
var rail = document.querySelector('.rail');
var out = document.getElementById('results');
var found = document.getElementById('found');
var timer = null;
var LIMIT = 300;
var ICON_MSG = '__ICON_MSG__';
var ICON_PIC = '__ICON_PIC__';

function el(tag, cls, text) {
  var node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function plural(count, one, many) {
  return Math.abs(count) === 1 ? one : many;
}

function volume(chat) {
  var host = el('span', 'vols');
  if (chat.i) {
    var pics = el('span', 'vol pics');
    var picsLabel = chat.i + ' ' + plural(chat.i, 'image', 'images');
    pics.title = picsLabel;
    pics.setAttribute('role', 'img');
    pics.setAttribute('aria-label', picsLabel);
    pics.innerHTML = ICON_PIC + '<span class="n">' + chat.i + '</span>';
    host.appendChild(pics);
  }
  var msgs = el('span', 'vol msgs');
  var msgsLabel = chat.m + ' ' + plural(chat.m, 'message', 'messages');
  msgs.title = msgsLabel;
  msgs.setAttribute('role', 'img');
  msgs.setAttribute('aria-label', msgsLabel);
  msgs.innerHTML = ICON_MSG + '<span class="n">' + chat.m + '</span>';
  host.appendChild(msgs);
  return host;
}

function context(text, lower, needle) {
  var at = lower.indexOf(needle);
  var host = el('div', 'ctx');
  if (at < 0) return host;
  var from = Math.max(0, at - 70);
  host.appendChild(document.createTextNode((from ? '...' : '') + text.slice(from, at)));
  host.appendChild(el('mark', null, text.slice(at, at + needle.length)));
  host.appendChild(document.createTextNode(text.slice(at + needle.length, at + needle.length + 110) + '...'));
  return host;
}

var corpus = null;
var original = null;
var waiting = null;

function withCorpus(done) {
  if (corpus) return done();
  if (waiting) {
    waiting = done;
    return;
  }
  waiting = done;
  found.textContent = 'loading full text...';
  var finish = function (data) {
    corpus = data;
    var pending = waiting;
    waiting = null;
    if (pending) pending();
  };
  var tag = document.createElement('script');
  tag.src = 'search-text.js';
  tag.onload = function () {
    var raw = window.CHAT_TEXT || [];
    var lower = new Array(raw.length);
    for (var i = 0; i < raw.length; i++) { lower[i] = raw[i].toLowerCase(); }
    original = raw;
    finish(lower);
  };
  tag.onerror = function () { finish([]); };
  document.head.appendChild(tag);
}

function render(needle) {
  var hits = [];
  for (var i = 0; i < CHATS.length && hits.length < LIMIT; i++) {
    var c = CHATS[i];
    if (c.lt === undefined) { c.lt = c.t.toLowerCase(); }
    var body = corpus[i] || '';
    var inText = body.indexOf(needle) >= 0;
    if (c.lt.indexOf(needle) >= 0 || inText) hits.push({ chat: c, at: i, text: inText });
  }
  found.textContent = hits.length < LIMIT ? 'found: ' + hits.length
    : 'found: more than ' + LIMIT;

  var host = el('div');
  for (var j = 0; j < hits.length; j++) {
    var chat = hits[j].chat;
    var row = el('div', 'hit');
    var link = el('a', null, chat.t);
    link.href = encodeURI(chat.u);
    row.appendChild(link);
    row.appendChild(volume(chat));
    row.appendChild(document.createTextNode(' '));
    row.appendChild(el('span', 'date', chat.d));
    if (hits[j].text) row.appendChild(context(original[hits[j].at], corpus[hits[j].at], needle));
    host.appendChild(row);
  }
  out.replaceChildren(host);
}

function search() {
  var needle = box.value.trim().toLowerCase();
  out.replaceChildren();
  if (needle.length < 2) {
    months.style.display = '';
    if (rail) rail.style.display = '';
    found.textContent = '';
    return;
  }
  months.style.display = 'none';
  if (rail) rail.style.display = 'none';
  withCorpus(function () {
    if (box.value.trim().toLowerCase() === needle) render(needle);
  });
}

function queryFromUrl() {
  var match = location.search.match(/[?&]q=([^&]*)/);
  if (!match) return '';
  try { return decodeURIComponent(match[1].replace(/\\+/g, ' ')); } catch (err) { return ''; }
}

// Запрос попадает в адресную строку, чтобы ссылкой на найденное можно было
// поделиться. На file:// история недоступна, поэтому промах не должен ломать поиск
function syncUrl(value) {
  if (!history.replaceState) return;
  try {
    var query = value ? '?q=' + encodeURIComponent(value) : '';
    history.replaceState(null, '', location.pathname + query + location.hash);
  } catch (err) {}
}

box.addEventListener('input', function () {
  clearTimeout(timer);
  timer = setTimeout(function () {
    syncUrl(box.value.trim());
    search();
  }, 160);
});

var fromUrl = queryFromUrl();
if (fromUrl && !box.value.trim()) { box.value = fromUrl; }
if (box.value.trim()) { search(); }
"""
    app = app.replace('__ICON_MSG__', ICON_MSG).replace('__ICON_PIC__', ICON_PIC)
    for name, body in (('style.css', css), ('theme.js', theme), ('chat.js', chat), ('app.js', app)):
        with open(os.path.join(SITE, 'assets', name), 'w', encoding='utf-8') as fh:
            fh.write(body.strip())

    katex_src = os.path.join(BASE, 'assets', 'katex')
    katex_dst = os.path.join(SITE, 'assets', 'katex')
    if os.path.isdir(katex_src) and not os.path.isdir(katex_dst):
        shutil.copytree(katex_src, katex_dst)


if __name__ == '__main__':
    sys.exit(main())
