from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = load_script('publish-release')
smoke = load_script('check-package-smoke')


class ReleasePipelineTests(unittest.TestCase):
    def test_notes_support_old_and_concise_layout_without_sentinel(self):
        for body in ('当前版本：`v1.0.0`\n本版详情：\n### 修复\n- 下载',
                     'v1.0.0\n### P1 · 安全\n- 修复下载\n### P2\n- 布局'):
            text = '# 下载\n## 版本说明\n' + body + '\n## 推荐下载\nold downloads'
            self.assertEqual(release.extract_notes(text, '1.0.0'), body + '\n')
        for body in ('v0.9.8\n- wrong version', 'v1.0.0 草稿\n- pending', 'v1.0.0'):
            with self.assertRaises(ValueError):
                release.extract_notes(body, '1.0.0')

    def assets(self, root):
        names = ['ilab-gpt-conjure_windows_portable_x64_1.0.0.zip',
                 'ilab-gpt-conjure_macos_portable_arm64_1.0.0.zip',
                 'ilab-gpt-conjure_macos_portable_x64_1.0.0.zip',
                 'iLab-GPT-CONJURE-windows-x64_1.0.0.zip',
                 'iLab-GPT-CONJURE-macos-arm64-1.0.0.dmg',
                 'iLab-GPT-CONJURE-macos-x64-1.0.0.dmg']
        for name in names:
            path = root / name
            path.write_bytes(b'synthetic archive')
            path.with_name(name + '.sha256.txt').write_text(hashlib.sha256(path.read_bytes()).hexdigest())
        return names

    def test_prepare_checks_all_packages_and_signs_before_external_writes(self):
        from tests.test_update_manifest import UpdateManifestTests
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = self.assets(root)
            source = root / 'source.md'
            source.write_text('## 版本说明\nv1.0.0\n### P1\n- 安全更新\n', encoding='utf-8')
            args = dict(directory=root, repo='example/project', tag='v1.0.0',
                        notes_source=source, notes=root / 'notes.md')
            with patch.dict(os.environ, {'ILAB_CONJURE_UPDATE_SIGNING_PRIVATE_KEY_B64': ''}), \
                    patch.object(release, 'gh') as external:
                with self.assertRaisesRegex(ValueError, 'signing key'):
                    release.prepare(**args)
                external.assert_not_called()
            with patch.dict(os.environ, {'ILAB_CONJURE_UPDATE_SIGNING_PRIVATE_KEY_B64': UpdateManifestTests.TEST_PRIVATE_KEY_PEM_B64}):
                files = release.prepare(**args)
                self.assertEqual(len(files), 13)
                manifest = json.loads((root / 'latest.json').read_text())
                self.assertIn('signature', manifest)
                self.assertIn('standard_signature', manifest)
                for name in names:
                    self.assertIn(name, args['notes'].read_text())
                (root / names[0]).write_bytes(b'corruption')
                with self.assertRaisesRegex(SystemExit, 'SHA256 mismatch'):
                    release.prepare(**args)

    def scenario(self, *, existing=False, published=False, upload_failure=False, bad_digest=False,
                 missing=False, lookup_failure=False, create_failure=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = root / 'latest.json'; asset.write_text('synthetic')
            notes = root / 'notes.md'; notes.write_text('notes')
            calls = []
            state = {'tag_name': 'v1.0.0', 'draft': not published, 'id': 7, 'prerelease': False}

            def fake(*args):
                calls.append(args)
                if args[0] == 'api' and '/git/ref/' in args[1]:
                    return json.dumps({'object': {'type': 'commit', 'sha': 'a' * 40}})
                if '--slurp' in args:
                    if lookup_failure:
                        raise subprocess.CalledProcessError(1, 'gh')
                    return json.dumps([[state] if existing else []])
                if args[:2] == ('release', 'create') and create_failure:
                    raise subprocess.CalledProcessError(1, 'gh')
                if args[:2] == ('release', 'upload') and upload_failure:
                    raise subprocess.CalledProcessError(1, 'gh')
                if args[0] == 'api' and '/assets?' in args[1]:
                    return json.dumps([] if missing else [{'name': asset.name, 'size': asset.stat().st_size,
                        'state': 'uploaded', 'digest': 'sha256:' + ('wrong' if bad_digest else release.digest(asset))}])
                if '--draft=false' in args:
                    state['draft'] = False
                return json.dumps(state)

            with patch.object(release, 'gh', side_effect=fake):
                try:
                    release.publish(repo='example/project', tag='v1.0.0', commit='a' * 40, files=[asset], notes=notes)
                except (ValueError, subprocess.CalledProcessError):
                    self.assertTrue(published or upload_failure or bad_digest or missing or lookup_failure or create_failure)
                else:
                    self.assertFalse(published or upload_failure or bad_digest or missing or lookup_failure or create_failure)
            return calls

    def test_draft_is_published_only_after_upload_and_digest_verification(self):
        calls = self.scenario()
        create = next(c for c in calls if c[:2] == ('release', 'create'))
        self.assertIn('--draft', create)
        self.assertIn('--verify-tag', create)
        publication = next(i for i, c in enumerate(calls) if '--draft=false' in c)
        check = next(i for i, c in enumerate(calls) if c[0] == 'api' and '/assets?' in c[1])
        self.assertGreater(publication, check)
        self.assertFalse(any(c[:2] == ('release', 'create') for c in self.scenario(existing=True)))

    def test_failures_never_publish_or_retry_creation(self):
        for flag in ('upload_failure', 'bad_digest', 'missing', 'lookup_failure', 'create_failure'):
            with self.subTest(flag=flag):
                calls = self.scenario(**{flag: True})
                self.assertFalse(any('--draft=false' in c for c in calls))
                self.assertLessEqual(sum(c[:2] == ('release', 'create') for c in calls), 1)
                if flag == 'lookup_failure':
                    self.assertTrue(all(c[0] == 'api' for c in calls))

    def test_published_release_is_not_modified(self):
        calls = self.scenario(existing=True, published=True)
        self.assertTrue(all(c[0] == 'api' for c in calls))

    def test_moved_tag_is_rejected(self):
        with patch.object(release, 'gh', return_value=json.dumps({'object': {'type': 'commit', 'sha': 'b' * 40}})) as call:
            with self.assertRaisesRegex(ValueError, 'verified CI commit'):
                release.publish(repo='example/project', tag='v1.0.0', commit='a' * 40, files=[], notes=Path('notes'))
            self.assertEqual(call.call_count, 1)

    def test_archive_integrity_and_traversal_rejected_before_unpacking(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'fixture.zip'
            for member, valid in [('app/file.txt', True), ('../outside.txt', False)]:
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr(member, 'synthetic')
                sidecar = path.with_name(path.name + '.sha256.txt')
                sidecar.write_text(smoke.file_hash(path))
                if valid:
                    smoke.verify_archive(path)
                else:
                    with self.assertRaisesRegex(ValueError, 'Unsafe'):
                        smoke.verify_archive(path)
            sidecar.write_text('0' * 64)
            with self.assertRaisesRegex(ValueError, 'checksum'):
                smoke.verify_archive(path)

    def test_packaged_server_failure_is_cleaned_up_with_isolated_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / 'package/resources/app'
            app.mkdir(parents=True)
            (app / 'standard_webui_app.py').touch()
            (app.parent / 'app-version.txt').write_text('1.0.0')
            python = app.parent / 'python/python.exe'
            python.parent.mkdir(); python.touch()
            process = MagicMock()
            process.poll.return_value = None
            opener = MagicMock()
            # Health succeeds, but the served version disagrees with the verified package.
            from io import BytesIO
            opener.open.side_effect = [BytesIO(b'{"ok":true}'), BytesIO(b'<html>ok</html>'),
                                       BytesIO(b'{"current_version":"0.9.8"}')]
            inventory = json.dumps({'python': '3.14.10', 'arch': 'AMD64', 'app': '1.0.0'})
            with patch.object(smoke.sys, 'platform', 'win32'), \
                    patch.object(smoke.subprocess, 'check_output', return_value=inventory), \
                    patch.object(smoke.subprocess, 'run'), \
                    patch.object(smoke.subprocess, 'Popen', return_value=process) as start, \
                    patch.object(smoke.urllib.request, 'build_opener', return_value=opener), \
                    patch.dict(os.environ, {'ILAB_CONJURE_BUNDLE_DIR': 'outside-fixture'}):
                with self.assertRaisesRegex(ValueError, 'application version mismatch'):
                    smoke.smoke(root / 'package', root, kind='standard', version='1.0.0',
                                arch='x64', python_version='3.14.10')
            process.terminate.assert_called_once()
            process.wait.assert_called_once()
            env = start.call_args.kwargs['env']
            self.assertEqual(env['ILAB_CONJURE_DATA_DIR'], str(root / 'data'))
            self.assertEqual(env['CODEX_HOME'], str(root / 'codex'))
            self.assertNotIn('ILAB_CONJURE_BUNDLE_DIR', env)

    def test_mounted_dmg_is_detached_even_when_validation_fails(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(smoke.subprocess, 'run') as command:
            with self.assertRaisesRegex(ValueError, 'probe failed'):
                with smoke.unpack(Path('synthetic.dmg'), Path(temporary)):
                    raise ValueError('probe failed')
            self.assertEqual(command.call_args_list[0].args[0][:2], ['hdiutil', 'attach'])
            self.assertEqual(command.call_args_list[-1].args[0][:2], ['hdiutil', 'detach'])


if __name__ == '__main__':
    unittest.main()
