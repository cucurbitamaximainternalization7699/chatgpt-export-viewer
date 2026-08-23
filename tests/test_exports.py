"""Edge-case tests for build_site.py.

Usage:
    python3 tests/test_exports.py

Each test builds a deliberately awkward export and checks that the generator
survives it and produces the expected pages.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, 'build_site.py')

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
       b'\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4'
       b'\x00\x00\x00\x00IEND\xaeB`\x82')


def msg(node_id, role, text, ctype='text', stamp=1717200000):
    return {
        'id': node_id,
        'author': {'role': role, 'name': None},
        'create_time': stamp,
        'content': {'content_type': ctype, 'parts': [text]},
        'metadata': {},
    }


def simple_conversation(cid='c1', title='Simple chat', pairs=2, stamp=1717200000):
    mapping = {'root': {'id': 'root', 'message': None, 'parent': None, 'children': []}}
    parent = 'root'
    for index in range(pairs):
        for role, text in (('user', 'Question %d' % index), ('assistant', 'Answer %d' % index)):
            node_id = '%s-%s-%d' % (cid, role, index)
            mapping[node_id] = {'id': node_id, 'message': msg(node_id, role, text, stamp=stamp),
                                'parent': parent, 'children': []}
            mapping[parent]['children'].append(node_id)
            parent = node_id
    return {
        'conversation_id': cid,
        'title': title,
        'create_time': stamp,
        'update_time': stamp + 600,
        'mapping': mapping,
        'current_node': parent,
    }


def write_zip(path, files):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, body in files.items():
            if isinstance(body, bytes):
                zf.writestr(name, body)
            else:
                zf.writestr(name, json.dumps(body, ensure_ascii=False))


def nested_zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, body in files.items():
            if isinstance(body, bytes):
                zf.writestr(name, body)
            else:
                zf.writestr(name, json.dumps(body, ensure_ascii=False))
    return buffer.getvalue()


def build(source, out):
    return subprocess.run([sys.executable, BUILD, source, out],
                          capture_output=True, text=True, timeout=600)


def read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def pages_in(out):
    site = os.path.join(out, 'site', 'chats')
    found = []
    for root, _, files in os.walk(site):
        found += [os.path.join(root, f) for f in files if f.endswith('.html')]
    return found


class ExportCases(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix='cev-test-')
        self.out = os.path.join(self.work, 'out')

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def zip_with(self, files, name='export.zip'):
        path = os.path.join(self.work, name)
        write_zip(path, files)
        return path

    def test_monolithic_conversations_json(self):
        source = self.zip_with({'conversations.json': [simple_conversation()]})
        run = build(source, self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 1)

    def test_sharded_export_with_manifest(self):
        shards = {
            'conversations-000.json': [simple_conversation('a', 'First')],
            'conversations-001.json': [simple_conversation('b', 'Second')],
            'export_manifest.json': {'logical_files': {'conversations.json': {
                'files': [{'name': 'conversations-000.json'}, {'name': 'conversations-001.json'}]}}},
        }
        run = build(self.zip_with(shards), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 2)

    def test_sharded_export_without_manifest(self):
        shards = {
            'conversations-000.json': [simple_conversation('a', 'First')],
            'conversations-001.json': [simple_conversation('b', 'Second')],
        }
        run = build(self.zip_with(shards), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 2)

    def test_nested_archive_holds_the_shards(self):
        inner = nested_zip_bytes({
            'conversations-000.json': [simple_conversation('a', 'First')],
            'conversations-001.json': [simple_conversation('b', 'Second')],
        })
        source = self.zip_with({
            'User Online Activity/Conversations__user-abc-chatgpt-0001.zip': inner,
            'README.txt': b'Privacy Portal export',
        })
        run = build(source, self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 2)

    def test_nested_archive_carries_its_attachments(self):
        conv = simple_conversation('a', 'With an image')
        node = 'a-user-0'
        conv['mapping'][node]['message']['content'] = {
            'content_type': 'multimodal_text',
            'parts': [{'content_type': 'image_asset_pointer', 'asset_pointer': 'file-service://file-nested1'}],
        }
        inner = nested_zip_bytes({
            'conversations-000.json': [conv],
            'file-nested1-shot.png': PNG,
        })
        source = self.zip_with({'User Online Activity/Conversations__user-abc.zip': inner})
        run = build(source, self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        pages = pages_in(self.out)
        self.assertEqual(len(pages), 1)
        self.assertIn('<img', read(pages[0]))

    def test_two_nested_archives_with_the_same_shard_names(self):
        first = nested_zip_bytes({'conversations-000.json': [simple_conversation('a', 'First')]})
        second = nested_zip_bytes({'conversations-000.json': [simple_conversation('b', 'Second')]})
        source = self.zip_with({
            'User Online Activity/Conversations__user-abc-0001.zip': first,
            'User Online Activity/Conversations__user-abc-0002.zip': second,
        })
        run = build(source, self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 2)

    def test_zip_attached_to_a_conversation_is_left_alone(self):
        attached = nested_zip_bytes({'conversations.json': [simple_conversation('x', 'Attached copy')]})
        source = self.zip_with({
            'conversations.json': [simple_conversation('a', 'Real chat')],
            'file-abc123-backup.zip': attached,
        })
        run = build(source, self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        pages = pages_in(self.out)
        self.assertEqual(len(pages), 1)
        self.assertIn('Real chat', read(pages[0]))

    def test_nested_archive_asset_names_are_restored(self):
        conv = simple_conversation('a', 'Photo chat')
        node = 'a-user-0'
        conv['mapping'][node]['message']['content'] = {
            'content_type': 'multimodal_text',
            'parts': [{'content_type': 'image_asset_pointer', 'asset_pointer': 'sediment://file_abc123'}],
        }
        inner = nested_zip_bytes({
            'conversations-000.json': [conv],
            'file_abc123.dat': PNG,
            'conversation_asset_file_names.json': {'file_abc123.dat': 'holiday-photo.png'},
        })
        source = self.zip_with({'User Online Activity/Conversations__user-abc.zip': inner})
        run = build(source, self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        stored = os.listdir(os.path.join(self.out, 'files'))
        self.assertEqual(len(stored), 1)
        self.assertIn('holiday-photo', stored[0])
        self.assertIn('alt="holiday-photo.png"', read(pages_in(self.out)[0]))

    def test_nested_archive_without_shards_is_skipped(self):
        useless = nested_zip_bytes({'notes.txt': b'nothing useful here'})
        source = self.zip_with({'User Online Activity/other.zip': useless})
        run = build(source, self.out)
        self.assertEqual(run.returncode, 1)
        self.assertIn('No conversations.json found', run.stdout)

    def test_broken_nested_archive_does_not_stop_the_build(self):
        good = nested_zip_bytes({'conversations-000.json': [simple_conversation('a', 'First')]})
        source = self.zip_with({
            'User Online Activity/broken.zip': b'PK\x03\x04 truncated beyond repair',
            'User Online Activity/Conversations__user-abc.zip': good,
        })
        run = build(source, self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 1)

    def test_only_the_first_nesting_level_is_opened(self):
        deepest = nested_zip_bytes({'conversations-000.json': [simple_conversation('a', 'Too deep')]})
        middle = nested_zip_bytes({'inner.zip': deepest})
        source = self.zip_with({'User Online Activity/outer.zip': middle})
        run = build(source, self.out)
        self.assertEqual(run.returncode, 1)
        self.assertIn('No conversations.json found', run.stdout)

    def test_manifest_listing_missing_shard(self):
        files = {
            'conversations-000.json': [simple_conversation()],
            'export_manifest.json': {'logical_files': {'conversations.json': {
                'files': [{'name': 'conversations-999.json'}]}}},
        }
        run = build(self.zip_with(files), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 1)

    def test_object_wrapper_instead_of_array(self):
        source = self.zip_with({'conversations.json': {'conversations': [simple_conversation()]}})
        run = build(source, self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 1)

    def test_missing_current_node_falls_back_to_latest_leaf(self):
        conv = simple_conversation(pairs=3)
        conv['current_node'] = None
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        page = read(pages_in(self.out)[0])
        self.assertIn('Answer 2', page)

    def test_current_node_pointing_nowhere(self):
        conv = simple_conversation()
        conv['current_node'] = 'does-not-exist'
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('Answer 1', read(pages_in(self.out)[0]))

    def test_mapping_without_children_arrays(self):
        conv = simple_conversation(pairs=3)
        for node in conv['mapping'].values():
            node.pop('children', None)
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        page = read(pages_in(self.out)[0])
        self.assertIn('Question 0', page)
        self.assertIn('Answer 2', page)

    def test_cycle_in_parent_links(self):
        conv = simple_conversation(pairs=2)
        ids = [key for key in conv['mapping'] if key != 'root']
        conv['mapping'][ids[0]]['parent'] = ids[-1]
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 1)

    def test_deep_chain_beyond_recursion_limit(self):
        mapping = {'root': {'id': 'root', 'message': None, 'parent': None, 'children': []}}
        parent = 'root'
        for index in range(1500):
            node_id = 'n%d' % index
            role = 'user' if index % 2 == 0 else 'assistant'
            mapping[node_id] = {'id': node_id, 'message': msg(node_id, role, 'line %d' % index),
                                'parent': parent, 'children': []}
            parent = node_id
        conv = {'conversation_id': 'deep', 'title': 'Deep thread', 'create_time': 1717200000,
                'update_time': 1717200000, 'mapping': mapping, 'current_node': parent}
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('line 1499', read(pages_in(self.out)[0]))

    def test_null_title_and_missing_timestamps(self):
        conv = simple_conversation()
        conv['title'] = None
        conv.pop('create_time')
        conv.pop('update_time')
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 1)

    def test_integer_and_null_timestamps_on_messages(self):
        conv = simple_conversation()
        stamps = [None, 1717200000, 1717200001.5]
        for index, node_id in enumerate(k for k in conv['mapping'] if k != 'root'):
            conv['mapping'][node_id]['message']['create_time'] = stamps[index % len(stamps)]
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_parts_with_objects_instead_of_strings(self):
        conv = simple_conversation()
        node_id = [k for k in conv['mapping'] if k != 'root'][0]
        conv['mapping'][node_id]['message']['content'] = {
            'content_type': 'multimodal_text',
            'parts': [{'content_type': 'image_asset_pointer',
                       'asset_pointer': 'sediment://file_deadbeef', 'width': 1, 'height': 1},
                      'text next to an image'],
        }
        files = {'conversations.json': [conv], 'file_deadbeef.dat': PNG,
                 'conversation_asset_file_names.json': {'file_deadbeef.dat': 'shot.png'}}
        run = build(self.zip_with(files), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        page = read(pages_in(self.out)[0])
        self.assertIn('<img', page)
        self.assertIn('text next to an image', page)

    def test_unknown_content_type_does_not_crash(self):
        conv = simple_conversation()
        node_id = [k for k in conv['mapping'] if k != 'root'][0]
        conv['mapping'][node_id]['message']['content'] = {
            'content_type': 'sonic_webpage_v9', 'parts': ['payload'], 'weird': {'nested': True}}
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 1)

    def test_nodes_without_message(self):
        conv = simple_conversation()
        conv['mapping']['orphan'] = {'id': 'orphan', 'message': None, 'parent': 'root',
                                     'children': []}
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_legacy_asset_naming(self):
        conv = simple_conversation()
        node_id = [k for k in conv['mapping'] if k != 'root'][0]
        conv['mapping'][node_id]['message']['content'] = {
            'content_type': 'multimodal_text',
            'parts': [{'content_type': 'image_asset_pointer',
                       'asset_pointer': 'file-service://file-Legacy123', 'width': 1, 'height': 1}]}
        files = {'conversations.json': [conv],
                 'dalle-generations/file-Legacy123-abc.webp': PNG}
        run = build(self.zip_with(files), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('<img', read(pages_in(self.out)[0]))

    def test_missing_attachment_is_reported(self):
        conv = simple_conversation()
        node_id = [k for k in conv['mapping'] if k != 'root'][0]
        conv['mapping'][node_id]['message']['content'] = {
            'content_type': 'multimodal_text',
            'parts': [{'content_type': 'image_asset_pointer',
                       'asset_pointer': 'sediment://file_gone', 'width': 1, 'height': 1}]}
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = os.path.join(self.out, 'missing-files.txt')
        self.assertTrue(os.path.exists(report))
        self.assertIn('file_gone', read(report))

    def test_truncated_zip_reports_error(self):
        source = self.zip_with({'conversations.json': [simple_conversation()]})
        with open(source, 'rb') as fh:
            data = fh.read()
        broken = os.path.join(self.work, 'broken.zip')
        with open(broken, 'wb') as fh:
            fh.write(data[:len(data) // 2])
        run = build(broken, self.out)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('Not a ZIP archive', run.stdout + run.stderr)
        self.assertNotIn('Traceback', run.stderr)

    def test_corrupt_json_skips_only_bad_shard(self):
        files = {
            'conversations-000.json': [simple_conversation('good', 'Readable')],
            'conversations-001.json': b'[{"broken": ',
        }
        run = build(self.zip_with(files), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(pages_in(self.out)), 1)

    def test_empty_export(self):
        run = build(self.zip_with({'conversations.json': []}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.out, 'site', 'index.html')))

    def test_no_conversations_file_at_all(self):
        run = build(self.zip_with({'user.json': {'id': 'x'}}), self.out)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('No conversations.json', run.stdout + run.stderr)

    def test_details_tags_keep_no_attributes(self):
        conv = simple_conversation()
        node_id = [k for k in conv['mapping'] if k != 'root'][0]
        conv['mapping'][node_id]['message']['content'] = {
            'content_type': 'text',
            'parts': ['<details open ontoggle="fetch(\'https://evil.example/\')" data-x="1">\n'
                      '<summary style="background:url(https://evil.example/pixel.png)">click</summary>\n'
                      'hidden text\n</details>'],
        }
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        body = read(pages_in(self.out)[0]).split('<main class="chat">', 1)[1].split('</main>', 1)[0]
        self.assertIn('<details open>', body)
        self.assertIn('<summary>', body)
        self.assertIn('hidden text', body)
        for leak in ('ontoggle', 'evil.example', 'data-x', 'style='):
            self.assertNotIn(leak, body)

    def test_multibyte_text_survives_chunk_boundaries(self):
        filler = 'a' * 500
        text = filler + 'мир 日本語 мир'
        conv = simple_conversation()
        node_id = [k for k in conv['mapping'] if k != 'root'][0]
        conv['mapping'][node_id]['message']['content'] = {'content_type': 'text', 'parts': [text]}
        payload = json.dumps([conv], ensure_ascii=False).encode('utf-8')

        from io import BytesIO
        sys.path.insert(0, ROOT)
        import build_site
        for chunk in (7, 16, 64, 257, 1024):
            restored = list(build_site.stream_json_array(BytesIO(payload), chunk))
            self.assertEqual(len(restored), 1, 'chunk %d lost the object' % chunk)
            body = restored[0]['mapping'][node_id]['message']['content']['parts'][0]
            self.assertEqual(body, text, 'chunk %d corrupted the text' % chunk)
            self.assertNotIn('�', json.dumps(restored, ensure_ascii=False))

    def test_source_that_is_not_an_archive(self):
        plain = os.path.join(self.work, 'notes.txt')
        with open(plain, 'w', encoding='utf-8') as fh:
            fh.write('just a text file')
        run = build(plain, self.out)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('Not a ZIP archive', run.stdout + run.stderr)
        self.assertNotIn('Traceback', run.stderr)

    def test_unwritable_output_reports_plainly(self):
        if os.name == 'nt' or os.geteuid() == 0:
            self.skipTest('permission bits behave differently here')
        blocked = os.path.join(self.work, 'blocked')
        os.makedirs(blocked)
        os.chmod(blocked, 0o500)
        try:
            run = build(self.zip_with({'conversations.json': [simple_conversation()]}),
                        os.path.join(blocked, 'out'))
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('Cannot write to', run.stdout + run.stderr)
            self.assertNotIn('Traceback', run.stderr)
        finally:
            os.chmod(blocked, 0o700)

    def test_unpacked_directory_matches_zip(self):
        conv = simple_conversation(pairs=3)
        source = self.zip_with({'conversations.json': [conv]})
        unpacked = os.path.join(self.work, 'unpacked')
        zipfile.ZipFile(source).extractall(unpacked)

        zip_out = os.path.join(self.work, 'from-zip')
        dir_out = os.path.join(self.work, 'from-dir')
        self.assertEqual(build(source, zip_out).returncode, 0)
        self.assertEqual(build(unpacked, dir_out).returncode, 0)

        from_zip = sorted(os.path.basename(p) for p in pages_in(zip_out))
        from_dir = sorted(os.path.basename(p) for p in pages_in(dir_out))
        self.assertEqual(from_zip, from_dir)

    def test_rebuild_removes_stale_pages(self):
        first = self.zip_with({'conversations.json': [simple_conversation('a', 'Old title')]},
                              name='first.zip')
        self.assertEqual(build(first, self.out).returncode, 0)
        second = self.zip_with({'conversations.json': [simple_conversation('a', 'New title')]},
                               name='second.zip')
        self.assertEqual(build(second, self.out).returncode, 0)
        names = [os.path.basename(p) for p in pages_in(self.out)]
        self.assertEqual(len(names), 1)
        self.assertIn('new-title', names[0])

    def test_titles_with_slashes_and_unicode(self):
        rough = simple_conversation('x', 'Отчёт / 2026: "черновик" <b>')
        run = build(self.zip_with({'conversations.json': [rough]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        page = pages_in(self.out)[0]
        self.assertNotIn('/', os.path.basename(page).replace('.html', ''))
        self.assertIn('&lt;b&gt;', read(page))

    def test_html_in_message_is_escaped(self):
        conv = simple_conversation()
        node_id = [k for k in conv['mapping'] if k != 'root'][0]
        conv['mapping'][node_id]['message']['content'] = {
            'content_type': 'text',
            'parts': ['<script>alert(1)</script> and <img src=x onerror=alert(2)>']}
        run = build(self.zip_with({'conversations.json': [conv]}), self.out)
        self.assertEqual(run.returncode, 0, run.stderr)
        page = read(pages_in(self.out)[0])
        body = page.split('<main class="chat">', 1)[1].split('</main>', 1)[0]
        self.assertNotIn('<script', body)
        self.assertNotIn('<img src=x', body)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', body)
        self.assertIn('&lt;img src=x onerror=alert(2)&gt;', body)


if __name__ == '__main__':
    unittest.main(verbosity=2)
