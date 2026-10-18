"""Guard the two inputs that the whole resource pipeline trusts.

`resource_sizes()` is the 18-file/18-size contract every later step assumes, and
`unpack_archives()` is the only thing standing between a downloaded archive and
the runner's filesystem. Both were previously exercised only through mocks.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]

spec = importlib.util.spec_from_file_location('ci', ROOT / 'scripts/ci.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def romfs_validate_source(count=18, size_count=None):
    size_count = count if size_count is None else size_count
    entries = ''.join(f'\n    "{i:02d}-resource-{i:02d}.data",' for i in range(1, count + 1))
    lengths = ', '.join(str(i) for i in range(1, size_count + 1))
    return (f'static const char *need[] = {{{entries}\n}};\n'
            f'static const long long size[] = {{ {lengths} }};\n')


class ResourceContractTests(unittest.TestCase):
    def write_source(self, text):
        (self.root / 'upstream/dm/host').mkdir(parents=True, exist_ok=True)
        (self.root / 'upstream/dm/host/romfs_validate.c').write_text(text)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(ci, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_reads_the_upstream_contract(self):
        self.write_source(romfs_validate_source())
        sizes = ci.resource_sizes()
        self.assertEqual(len(sizes), 18)
        self.assertEqual(sizes['01-resource-01.data'], 1)
        self.assertEqual(sizes['18-resource-18.data'], 18)

    def test_rejects_a_partial_manifest(self):
        for count in (17, 19):
            with self.subTest(files=count):
                self.write_source(romfs_validate_source(count=count))
                with self.assertRaisesRegex(ValueError, 'Unexpected upstream resource manifest'):
                    ci.resource_sizes()

    def test_rejects_mismatched_name_and_size_counts(self):
        self.write_source(romfs_validate_source(count=18, size_count=17))
        with self.assertRaisesRegex(ValueError, 'Unexpected upstream resource manifest'):
            ci.resource_sizes()

    def test_rejects_missing_tables(self):
        self.write_source('// no manifest here\n')
        with self.assertRaises(AttributeError):
            ci.resource_sizes()


class ArchiveGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.patch = patch.object(ci, 'WORK', self.work)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        (self.work / 'evil.zip').write_bytes(b'PK\x03\x04')

    def listing(self, *members):
        return ''.join(f'Path = {m}\n' for m in (str(self.work / 'evil.zip'), *members))

    def test_rejects_members_that_escape_the_extraction_directory(self):
        unsafe = ('../../etc/passwd', '/etc/passwd', 'C:\\Windows\\evil.dll',
                  'payload/../../etc/passwd', '..\\..\\evil.dll', '/', '..')
        for member in unsafe:
            with self.subTest(member=member):
                (self.work / 'evil.zip').write_bytes(b'PK\x03\x04')
                with patch.object(ci.subprocess, 'check_output', return_value=self.listing(member)), \
                     patch.object(ci, 'run', side_effect=AssertionError('extracted an unsafe member')):
                    with self.assertRaisesRegex(ValueError, 'Unsafe archive member path'):
                        ci.unpack_archives()

    def test_extracts_ordinary_members(self):
        calls = []
        with patch.object(ci.subprocess, 'check_output',
                          return_value=self.listing('payload/good.bin', 'a/b/c.txt')), \
             patch.object(ci, 'run', side_effect=lambda args, log, env=None: calls.append(args)):
            ci.unpack_archives()
        self.assertEqual(len(calls), 1)
        self.assertIn('-o' + str(self.work / 'evil.zip.unpacked'), calls[0])

    def test_skips_continuation_volumes_but_removes_them(self):
        (self.work / 'evil.zip').unlink()
        first, second = self.work / 'pack.part1.rar', self.work / 'pack.part2.rar'
        first.write_bytes(b'Rar!')
        second.write_bytes(b'Rar!')
        calls = []
        with patch.object(ci.subprocess, 'check_output', return_value=self.listing('payload/good.bin')), \
             patch.object(ci, 'run', side_effect=lambda args, log, env=None: calls.append(args)):
            ci.unpack_archives()
        self.assertEqual([Path(a[-1]).name for a in calls], ['pack.part1.rar'])
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())


if __name__ == '__main__':
    unittest.main()
