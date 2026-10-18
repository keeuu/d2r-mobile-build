"""Tests for the release bump tool's refusal paths, with no network access."""
import importlib.util
import io
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('bump_upstream', ROOT / 'scripts/bump_upstream.py')
bump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bump)


def shell_zip(path, info='PRODUCT=1.2.3-r44\nCHAIN=abc\nKIND=ios\nSHADER_SRC=def\nSPIRV_CROSS=1.4\n',
              manifest=b'dm/a.dat\n', info_count=1, manifest_count=1):
    with zipfile.ZipFile(path, 'w') as archive:
        for index in range(info_count):
            archive.writestr(f'Payload/DmIOS{index}.app/dm/shell_info.txt', info)
        for index in range(manifest_count):
            archive.writestr(f'Payload/DmIOSm{index}.app/dm/shell_manifest.txt', manifest)
    return path


class HashPolicyTests(unittest.TestCase):
    """A new release without an official checksum file must not be pinned silently."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dest = Path(self.temp.name)

    def _run(self, required):
        with mock.patch.object(bump, 'release_assets', return_value={'SHA256SUMS.txt': self.dest / 'missing.txt'}):
            with redirect_stdout(io.StringIO()) as out:
                result = bump.official_hashes('owner/repo', 'v9.9.9', self.dest, required)
        return result, out.getvalue()

    def test_missing_checksum_file_is_refused_for_a_new_pin(self):
        with self.assertRaises(RuntimeError) as caught:
            self._run(required=True)
        self.assertIn('SHA256SUMS.txt', str(caught.exception))
        self.assertIn('--accept-unverified-hashes', str(caught.exception))

    def test_missing_checksum_file_is_only_a_note_when_reverifying_the_pin(self):
        result, output = self._run(required=False)
        self.assertEqual(result, {})
        self.assertIn('no SHA256SUMS.txt', output)


class ShellArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def _archive(self, name, **kwargs):
        return shell_zip(Path(self.temp.name) / name, **kwargs)

    def test_one_shell_info_and_manifest_are_read(self):
        info, manifest = bump.shell_facts(self._archive('a.zip'))
        self.assertEqual(info['PRODUCT'], '1.2.3-r44')
        self.assertEqual(info['SPIRV_CROSS'], '1.4')
        self.assertEqual(manifest, b'dm/a.dat\n')

    def test_ambiguous_shell_info_is_refused(self):
        for kwargs in ({'info_count': 0}, {'info_count': 2}, {'manifest_count': 0}, {'manifest_count': 2}):
            with self.subTest(**kwargs):
                with self.assertRaises(RuntimeError):
                    bump.shell_facts(self._archive('b.zip', **kwargs))


class RewriteTests(unittest.TestCase):
    def test_rewrite_replaces_once_then_reports_no_change(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'README.md'
            path.write_text('use D2RMobile-v1.0.17.ipa and v1.0.17')
            self.assertTrue(bump.rewrite(path, [('v1.0.17', 'v1.0.18')], dry_run=False))
            self.assertEqual(path.read_text(), 'use D2RMobile-v1.0.18.ipa and v1.0.18')
            self.assertFalse(bump.rewrite(path, [('v1.0.17', 'v1.0.18')], dry_run=False))

    def test_dry_run_leaves_the_file_alone(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'README.md'
            path.write_text('v1.0.17')
            self.assertTrue(bump.rewrite(path, [('v1.0.17', 'v1.0.18')], dry_run=True))
            self.assertEqual(path.read_text(), 'v1.0.17')


class ShippedTreeTests(unittest.TestCase):
    """The tool must agree with the config it is about to rewrite."""

    def test_repo_slugs_and_config_keys_exist(self):
        config = bump.json.loads(bump.CONFIG_PATH.read_text())
        for key in ('upstream_repository', 'upstream_commit', 'shell_url', 'shell_sha256',
                    'ios18_shell_url', 'ios18_shell_sha256', 'game_version'):
            self.assertIn(key, config)
        self.assertTrue((ROOT / 'tests').is_dir())
        for name in bump.README_NAMES:
            self.assertTrue((ROOT / name).is_file())
        self.assertEqual(bump.ci.sha256.__module__, 'ci')

    def test_every_release_asset_name_is_used_by_the_config(self):
        config = bump.json.loads(bump.CONFIG_PATH.read_text())
        for name in bump.SHELL_ASSETS:
            self.assertTrue(config['shell_url'].endswith('/' + name) or config['ios18_shell_url'].endswith('/' + name),
                            f'{name} is not referenced by build-config.json')

    def test_source_files_match_the_build_contract(self):
        # ci.py reads these exact paths when it checks the pinned source.
        self.assertIn('dm/PRODUCT', bump.SOURCE_FILES)
        self.assertIn('dm/host/romfs_validate.c', bump.SOURCE_FILES)
        self.assertIn('dm/gfx/tools/dmsh_chain.py', bump.SOURCE_FILES)
        self.assertEqual(bump.INFO_KEYS, {'PRODUCT', 'CHAIN', 'KIND', 'SHADER_SRC', 'SPIRV_CROSS'})


if __name__ == '__main__':
    unittest.main()
