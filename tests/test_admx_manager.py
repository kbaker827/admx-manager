"""Tests for ADMX Manager (standard library only: python -m unittest)"""

import functools
import http.server
import io
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import zipfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import admx_manager as am  # noqa: E402


def write(path, data=b''):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def make_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue()


class SafeFilenameTests(unittest.TestCase):
    def test_replaces_windows_invalid_characters(self):
        self.assertEqual(am.safe_filename('details.aspx?id=1'), 'details.aspx_id=1')
        self.assertEqual(am.safe_filename('a<b>c:d"e|f*g'), 'a_b_c_d_e_f_g')

    def test_empty_uses_fallback(self):
        self.assertEqual(am.safe_filename(' . ', 'x'), 'x')


class FilenameFromResponseTests(unittest.TestCase):
    def test_uses_url_path(self):
        self.assertEqual(
            am.filename_from_response('https://dl.google.com/chrome/policy/policy_templates.zip'),
            'policy_templates.zip')

    def test_query_string_is_not_part_of_name(self):
        self.assertEqual(
            am.filename_from_response('https://go.microsoft.com/fwlink/?linkid=2099616', fallback='Edge.zip'),
            'Edge.zip')

    def test_content_disposition_wins(self):
        self.assertEqual(
            am.filename_from_response('https://x/fwlink', 'attachment; filename="Edge Policy.cab"'),
            'Edge Policy.cab')

    def test_content_disposition_cannot_escape_folder(self):
        self.assertEqual(
            am.filename_from_response('https://x/y', 'attachment; filename="..\\..\\evil.zip"'),
            'evil.zip')

    def test_rfc5987_filename(self):
        self.assertEqual(
            am.filename_from_response('https://x/y', "attachment; filename*=UTF-8''my%20file.zip"),
            'my file.zip')


class DetectFileTypeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def check(self, data, expected):
        path = write(os.path.join(self.tmp.name, 'f'), data)
        self.assertEqual(am.detect_file_type(path), expected)

    def test_types(self):
        self.check(make_zip({'a.txt': 'x'}), 'zip')
        self.check(b'MSCF\0\0\0\0', 'cab')
        self.check(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest', 'msi')
        self.check(b'\n  <!DOCTYPE html><html>', 'html')
        self.check(b'\xef\xbb\xbf<HTML><body>', 'html')
        # A directly downloaded .admx is XML, not a web page
        self.check(b'\xef\xbb\xbf<?xml version="1.0"?><policyDefinitions>', None)
        self.check(b'random', None)


class LanguageFolderTests(unittest.TestCase):
    def test_language_folders(self):
        for name in ('en-US', 'de-DE', 'sr-Latn-RS', 'zh-CN', 'es-419'):
            self.assertTrue(am.is_language_folder(name), name)
        for name in ('admx', 'adm', 'windows', 'en', 'PolicyDefinitions', 'policy_templates'):
            self.assertFalse(am.is_language_folder(name), name)


class PolicyFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def test_find_is_case_insensitive(self):
        write(os.path.join(self.root, 'a', 'chrome.admx'))
        write(os.path.join(self.root, 'a', 'WINDOWS.ADMX'))
        write(os.path.join(self.root, 'a', 'en-US', 'chrome.adml'))
        write(os.path.join(self.root, 'a', 'chrome.adm'))
        admx, adml = am.find_policy_files(self.root)
        self.assertEqual(sorted(os.path.basename(f) for f in admx), ['WINDOWS.ADMX', 'chrome.admx'])
        self.assertEqual([os.path.basename(f) for f in adml], ['chrome.adml'])

    def test_plan_places_adml_in_language_folder(self):
        admx = [os.path.join('src', 'chrome.admx')]
        adml = [os.path.join('src', 'de-DE', 'chrome.adml'),
                os.path.join('src', 'sr-Latn-RS', 'chrome.adml'),
                os.path.join('src', 'loose', 'other.adml')]
        plan = am.plan_policy_copy(admx, adml, 'dest')
        self.assertEqual([dst for _src, dst in plan], [
            os.path.join('dest', 'chrome.admx'),
            os.path.join('dest', 'de-DE', 'chrome.adml'),
            os.path.join('dest', 'sr-Latn-RS', 'chrome.adml'),
            os.path.join('dest', 'en-US', 'other.adml'),
        ])

    def test_duplicates_and_missing_adml(self):
        admx = [os.path.join('a', 'google.admx'), os.path.join('b', 'google.admx'), os.path.join('a', 'x.admx')]
        adml = [os.path.join('a', 'en-US', 'google.adml')]
        plan = am.plan_policy_copy(admx, adml, 'dest')
        self.assertEqual(am.duplicate_targets(plan), [os.path.join('dest', 'google.admx')])
        self.assertEqual(am.admx_missing_adml(admx, adml), ['x.admx'])


class ResolveDownloadUrlTests(unittest.TestCase):
    def test_direct_url(self):
        self.assertEqual(am.resolve_download_url({'direct_url': 'https://x/y.zip'}), 'https://x/y.zip')

    def test_page_only_source_is_manual(self):
        self.assertIsNone(am.resolve_download_url({'url': 'https://example.com/page'}))

    def test_github_latest_release_from_redirect(self):
        location = 'https://github.com/mozilla/policy-templates/releases/download/v8.3/policy_templates_latest.zip'
        opener = mock.Mock(side_effect=urllib.error.HTTPError(
            'https://github.com/x', 302, 'Found', {'Location': location}, None))
        info = am.ADMXManager.DEFAULT_SOURCES['Mozilla Firefox']
        self.assertEqual(
            am.resolve_download_url(info, opener),
            'https://github.com/mozilla/policy-templates/releases/download/v8.3/policy_templates_v8.3.zip')
        request = opener.call_args[0][0]
        self.assertEqual(request.get_method(), 'HEAD')
        self.assertIn('/releases/latest/download/', request.full_url)

    def test_github_latest_release_other_error_raises(self):
        opener = mock.Mock(side_effect=urllib.error.HTTPError('https://github.com/x', 404, 'Not Found', {}, None))
        with self.assertRaises(urllib.error.HTTPError):
            am.resolve_download_url(am.ADMXManager.DEFAULT_SOURCES['Mozilla Firefox'], opener)

    def test_github_tag_from_url(self):
        self.assertEqual(am.github_tag_from_url('https://github.com/o/r/releases/tag/v1.2'), 'v1.2')
        self.assertEqual(am.github_tag_from_url('https://github.com/o/r/releases/download/v1.2/a.zip'), 'v1.2')
        self.assertIsNone(am.github_tag_from_url('https://github.com/o/r/releases'))


class DefaultSourceTests(unittest.TestCase):
    def test_sources_are_well_formed(self):
        for name, info in am.ADMXManager.DEFAULT_SOURCES.items():
            self.assertTrue(info.get('url', '').startswith('https://'), name)
            self.assertIn(info.get('category'), am.ADMXManager.BASE_CATEGORIES, name)
            direct = info.get('direct_url')
            if direct:
                self.assertTrue(direct.startswith('https://'), name)


class ExtractArchiveTests(unittest.TestCase):
    def test_extracts_nested_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            inner = make_zip({'windows/admx/msedge.admx': '<policyDefinitions/>'})
            outer = write(os.path.join(tmp, 'outer.zip'), make_zip({'Templates.zip': inner}))
            logs = []
            self.assertTrue(am.extract_archive(outer, os.path.join(tmp, 'out'), logs.append))
            admx, _adml = am.find_policy_files(os.path.join(tmp, 'out'))
            self.assertEqual([os.path.basename(f) for f in admx], ['msedge.admx'])


def _tk_available():
    if am.tk is None:
        return False
    try:
        root = am.tk.Tk()
        root.destroy()
        return True
    except am.tk.TclError:
        return False


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(_tk_available(), "Tk display not available")
class GuiSmokeTests(unittest.TestCase):
    def setUp(self):
        self.root = am.tk.Tk()
        self.root.withdraw()
        self.app = am.ADMXManager(self.root)
        self.addCleanup(self.root.destroy)
        self.addCleanup(lambda: self.root.after_cancel(self.app._ui_after_id))

    def pump(self, until, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.root.update()
            if until():
                return
            time.sleep(0.02)
        self.fail("timed out")

    def test_lists_and_filters_sources(self):
        self.assertEqual(len(self.app.tree.get_children()), len(am.ADMXManager.DEFAULT_SOURCES))
        self.app.category_var.set('Browser')
        self.app.filter_sources()
        self.assertEqual(set(self.app.tree.get_children()),
                         {'Microsoft Edge', 'Google Chrome', 'Mozilla Firefox'})
        self.app.search_var.set('chrome')
        self.assertEqual(self.app.tree.get_children(), ('Google Chrome',))

    def test_selection_survives_reload(self):
        self.app.select_all()
        self.app.admx_sources['Custom'] = {'url': 'https://x/y.zip', 'direct_url': 'https://x/y.zip',
                                           'publisher': 'Me', 'category': 'Internal'}
        self.app.load_sources()
        self.assertTrue(self.app.selected_sources['Google Chrome'])
        self.assertFalse(self.app.selected_sources['Custom'])
        self.assertIn('Internal', self.app.category_combo.cget('values'))

    def test_details_panel(self):
        self.app.tree.selection_set('Mozilla Firefox')
        self.root.update()
        text = self.app.details_text.get('1.0', 'end')
        self.assertIn('Latest release of github.com/mozilla/policy-templates', text)

    def test_download_and_extract_from_local_server(self):
        with tempfile.TemporaryDirectory() as serve, tempfile.TemporaryDirectory() as dest:
            write(os.path.join(serve, 'templates.zip'), make_zip({
                'windows/admx/test.admx': '<policyDefinitions/>',
                'windows/admx/en-US/test.adml': '<policyDefinitionResources/>',
            }))
            write(os.path.join(serve, 'page.html'), b'<!DOCTYPE html><html></html>')

            handler = functools.partial(QuietHandler, directory=serve)
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            base = f'http://127.0.0.1:{server.server_address[1]}'

            self.app.admx_sources = {
                'Good': {'direct_url': base + '/templates.zip', 'publisher': 'Test', 'category': 'Other'},
                'Web page': {'direct_url': base + '/page.html', 'publisher': 'Test', 'category': 'Other'},
                'Missing': {'direct_url': base + '/nope.zip', 'publisher': 'Test', 'category': 'Other'},
            }
            self.app.load_sources()
            self.app.select_all()
            self.app.download_path_var.set(dest)

            with mock.patch.object(am.messagebox, 'showwarning') as warning:
                self.app.download_selected()
                self.pump(lambda: not self.app.busy)
                self.pump(lambda: warning.called)

            summary = warning.call_args[0][1]
            self.assertIn('Downloaded 1/3', summary)
            self.assertIn('Web page', summary)
            self.assertIn('Missing', summary)

            admx, adml = am.find_policy_files(dest)
            self.assertEqual([os.path.basename(f) for f in admx], ['test.admx'])
            self.assertEqual([os.path.basename(f) for f in adml], ['test.adml'])
            self.assertIn(os.path.join('Test', 'Other', 'templates', 'windows'), admx[0])
            self.assertEqual(self.app.progress_var.get(), 100)


if __name__ == '__main__':
    unittest.main()
