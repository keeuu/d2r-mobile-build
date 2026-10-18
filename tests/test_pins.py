"""The pinned upstream release must stay in step with the workflows and the READMEs.

Every mismatch these tests cover has already happened once in this repository:
the source commit was pinned in both build-config.json and pack.yml, the game
payload path was written out by hand in three places, and the READMEs went two
upstream releases stale while the build moved on.
"""
import importlib.util
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]

spec = importlib.util.spec_from_file_location('ci', ROOT / 'scripts/ci.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)

README_NAMES = ('README.md', 'README.zh-CN.md')
IPA_NAME = re.compile(r'D2RMobile-v\d+\.\d+(?:\.\d+)?(?:-ios18)?\.ipa')
UPSTREAM_ROW = re.compile(r'\|\s*(?:Upstream|上游)\s*\|\s*(v\d+\.\d+(?:\.\d+)?)\s*\|')
CONFIG_ONLY_SCRIPTS = ('scripts/ci.py', 'scripts/export_resources.py', 'scripts/legacy_pack.py',
                       'scripts/publish_release.py', 'scripts/release_notes.py', 'scripts/build_ipas.py',
                       'scripts/bump_upstream.py')


class PinnedReleaseTests(unittest.TestCase):
    def test_both_shells_come_from_one_release_with_pinned_hashes(self):
        version = ci.upstream_version()
        self.assertRegex(ci.CONFIG['upstream_commit'], r'^[0-9a-f]{40}$')
        for url_key, hash_key in (('shell_url', 'shell_sha256'),
                                  ('ios18_shell_url', 'ios18_shell_sha256')):
            with self.subTest(url=url_key):
                self.assertTrue(ci.CONFIG[url_key].startswith(
                    'https://github.com/jhaizhou-ops/d2r-mobile/releases/download/'))
                self.assertIn(f'/releases/download/{version}/', ci.CONFIG[url_key])
                self.assertRegex(ci.CONFIG[hash_key], r'^[0-9a-f]{64}$')
        # Upstream ships build inputs, not installable IPAs; the names must differ
        # so the two variants cannot be confused for one another.
        self.assertNotEqual(ci.CONFIG['shell_url'], ci.CONFIG['ios18_shell_url'])
        for ipa in ci.ipa_names():
            self.assertTrue(ipa.endswith('.ipa'))

    def test_the_source_commit_lives_only_in_build_config(self):
        workflows = sorted((ROOT / '.github/workflows').glob('*.yml'))
        self.assertTrue(workflows)
        for workflow in workflows:
            # Action pins are 40-hex too; only a bare literal is a source pin.
            text = re.sub(r'@[0-9a-f]{40}\b', '@<pinned-action>', workflow.read_text())
            with self.subTest(workflow=workflow.name):
                self.assertNotRegex(
                    text, r'\b[0-9a-f]{40}\b',
                    'Read the pinned commit from build-config.json, not a workflow literal')
        self.assertIn('steps.pin.outputs.commit', (ROOT / '.github/workflows/pack.yml').read_text())

    def test_the_game_payload_path_is_derived_not_written_out(self):
        # The game version used to be repeated as a literal cache path in the
        # workflow; it now only reaches the runner through build-config.json.
        pack = (ROOT / '.github/workflows/pack.yml').read_text()
        self.assertNotRegex(pack, r'data/switch/[^$]',
                            'Derive the game payload path from build-config.json')
        self.assertIn(ci.CONFIG['game_version'], ci.GAME.parts)

    def test_scripts_read_the_game_version_from_config(self):
        for name in CONFIG_ONLY_SCRIPTS:
            text = (ROOT / name).read_text()
            with self.subTest(script=name):
                self.assertNotIn(ci.CONFIG['game_version'], text)
                self.assertNotIn(ci.CONFIG['switch_version'], text)

    def test_the_shell_toolchain_is_pinned_with_a_version(self):
        # The shell only accepts shaders from one exact spirv-cross build. Pinning
        # the version next to the commit lets the bump tool notice a toolchain
        # change before a 20 minute build fails on a shader digest mismatch.
        self.assertRegex(ci.CONFIG['spirv_cross_version'], r'^\d+(\.\d+){2,}$')
        self.assertRegex(ci.CONFIG['spirv_commit'], r'^[0-9a-f]{40}$')
        tools = (ROOT / 'scripts/tools.sh').read_text()
        self.assertIn('spirv_commit', tools, 'tools.sh must read the pin from build-config.json')
        self.assertNotIn(ci.CONFIG['spirv_commit'], tools, 'The spirv-cross commit must not be hardcoded')

    def test_cache_revision_default_tracks_the_game_version(self):
        defaults = set(re.findall(r'default: (game-\S+)',
                                  (ROOT / '.github/workflows/pack.yml').read_text()))
        self.assertTrue(defaults, 'Expected an input_revision default')
        for value in defaults:
            self.assertIn(ci.CONFIG['game_version'], value)

    def test_readmes_name_the_release_that_is_actually_built(self):
        names, version = set(ci.ipa_names()), ci.upstream_version()
        statements = {}
        for name in README_NAMES:
            text = (ROOT / name).read_text()
            found, rows = set(IPA_NAME.findall(text)), set(UPSTREAM_ROW.findall(text))
            with self.subTest(readme=name):
                self.assertEqual(found, names, f'{name} must name the IPA files this build produces')
                self.assertEqual(rows, {version}, f'{name} must state upstream {version}')
            statements[name] = (found, rows)
        self.assertEqual(statements['README.md'], statements['README.zh-CN.md'],
                         'Both READMEs must describe the same release')


    def test_readme_step_numbering_is_contiguous(self):
        # Adding a step in one README but not the other, or renumbering by hand,
        # has already produced two sections numbered 3.
        structures = {}
        for name in README_NAMES:
            sections, current = [], None
            for line in (ROOT / name).read_text().splitlines():
                if line.startswith('## '):
                    current = []
                    sections.append(current)
                step = re.match(r'### (\d+)\. ', line)
                if step and current is not None:
                    current.append(int(step.group(1)))
            with self.subTest(readme=name):
                for index, steps in enumerate(sections, 1):
                    if steps:
                        self.assertEqual(steps, list(range(1, len(steps) + 1)),
                                         f'{name} section {index} step numbering: {steps}')
            structures[name] = sections
        self.assertEqual(structures['README.md'], structures['README.zh-CN.md'],
                         'Both READMEs must have the same step structure')

    def test_both_readmes_document_the_release_bump_tool(self):
        tool = 'scripts/bump_upstream.py'
        self.assertTrue((ROOT / tool).is_file())
        for name in README_NAMES:
            with self.subTest(readme=name):
                self.assertIn(tool, (ROOT / name).read_text(),
                              f'{name} must tell maintainers how to move to a new upstream release')


if __name__ == "__main__":
    unittest.main()
