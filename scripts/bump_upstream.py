#!/usr/bin/env python3
"""Move the pinned upstream release to another published version.

    python scripts/bump_upstream.py              # the latest published release
    python scripts/bump_upstream.py v1.0.18      # a specific tag
    python scripts/bump_upstream.py --check      # verify the current pin, change nothing

Nothing is written until the new release passes every check the build itself will
later rely on:

* both shell build inputs match the release's own ``SHA256SUMS.txt``;
* both shells report the same program and shader requirements, and the same
  content manifest, so one generated payload can be shared between them;
* the pinned source provides every file the build reads, and the resource
  contract is still the expected 18 files and 18 sizes;
* the shell's PRODUCT still matches ``dm/PRODUCT`` at the pinned commit.

If the game version moved, the run reports that the Data release has to be
regenerated; if it did not, the existing Data is reused and nothing is re-uploaded.
"""
import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ci  # noqa: E402

ROOT = ci.ROOT
CONFIG_PATH = ROOT / 'build-config.json'
README_NAMES = ('README.md', 'README.zh-CN.md')
SHELL_ASSETS = ('D2RMobile-shell-build-input.zip', 'D2RMobile-shell-ios18-build-input.zip')
# Files the build reads out of the checked-out source, with what each must satisfy.
SOURCE_FILES = ('dm/PRODUCT', 'dm/host/romfs_validate.c', 'dm/gfx/tools/dmsh_chain.py',
                'dm/gfx/tools/nometal_run.py', 'dm/tools/d2rm_pack.py', 'dm/tools/dmx.py')
MANIFEST_SUFFIX = '/dm/shell_manifest.txt'
INFO_SUFFIX = '/dm/shell_info.txt'
INFO_KEYS = {'PRODUCT', 'CHAIN', 'KIND', 'SHADER_SRC', 'SPIRV_CROSS'}


def gh(*args):
    result = subprocess.run(['gh', *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {result.stderr.strip()}")
    return result.stdout


def api(path):
    return json.loads(gh('api', path))


def resolve_commit(repo, tag):
    ref = api(f'repos/{repo}/git/ref/tags/{tag}')['object']
    if ref['type'] == 'tag':  # annotated tag: dereference to the commit
        ref = api(f'repos/{repo}/git/tags/{ref["sha"]}')['object']
    return ref['sha']


def source_file(repo, commit, path):
    payload = api(f'repos/{repo}/contents/{path}?ref={commit}')
    if payload.get('encoding') != 'base64':
        raise RuntimeError(f'Unexpected encoding for {path}')
    return base64.b64decode(payload['content']).decode()


def release_assets(repo, tag, names, dest):
    gh('release', 'download', tag, '--repo', repo, '--dir', str(dest), '--clobber',
       *[f'--pattern={name}' for name in names])
    return {name: dest / name for name in names}


def official_hashes(repo, tag, dest, required):
    """Read the release's own SHA256SUMS.txt; refuse to pin a new release without one."""
    path = release_assets(repo, tag, ('SHA256SUMS.txt',), dest)['SHA256SUMS.txt']
    if not path.is_file() or not path.stat().st_size:
        if required:
            raise RuntimeError(
                f'{tag} publishes no SHA256SUMS.txt, so the shell hashes cannot be cross-checked '
                'against the release. Re-run with --accept-unverified-hashes to pin locally '
                'computed hashes instead.')
        print(f'  {tag} publishes no SHA256SUMS.txt; hashes are only checked against build-config.json')
        return {}
    hashes = {}
    for line in path.read_text().splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            hashes[name.strip().lstrip('*')] = digest.strip().lower()
    return hashes


def shell_facts(path):
    with zipfile.ZipFile(path) as archive:
        infos = [n for n in archive.namelist() if n.endswith(INFO_SUFFIX)]
        manifests = [n for n in archive.namelist() if n.endswith(MANIFEST_SUFFIX)]
        if len(infos) != 1 or len(manifests) != 1:
            raise RuntimeError(f'{path.name}: expected exactly one shell_info.txt and shell_manifest.txt')
        info = dict(line.split('=', 1) for line in archive.read(infos[0]).decode().splitlines() if '=' in line)
        return info, archive.read(manifests[0])


def verify(repo, tag, dest, require_official):
    """Return the verified pin for ``tag``, or raise with the reason it is unusable."""
    commit = resolve_commit(repo, tag)
    target = api(f'repos/{repo}/releases/tags/{tag}').get('target_commitish')
    if target and target != commit:
        print(f'  note: release target_commitish {target[:12]} != tag commit {commit[:12]}; using the tag')

    files = release_assets(repo, tag, (*SHELL_ASSETS,), dest)
    hashes = official_hashes(repo, tag, dest, require_official)
    digests = {}
    for name, path in files.items():
        if not path.is_file():
            raise RuntimeError(f'{tag} does not publish {name}')
        digests[name] = ci.sha256(path)
        if name in hashes:
            if hashes[name] != digests[name]:
                raise RuntimeError(f'{name}: SHA256SUMS.txt says {hashes[name]}, file is {digests[name]}')
            print(f'  {name}: {digests[name]} (matches SHA256SUMS.txt)')
        else:
            print(f'  {name}: {digests[name]} (computed locally, unverified)')

    first_info, first_manifest = shell_facts(files[SHELL_ASSETS[0]])
    other_info, other_manifest = shell_facts(files[SHELL_ASSETS[1]])
    if first_info != other_info:
        raise RuntimeError(f'The two shells disagree on program or shader requirements: {first_info} vs {other_info}')
    missing = INFO_KEYS - first_info.keys()
    if missing:
        raise RuntimeError(f'shell_info.txt is missing {sorted(missing)}')
    if first_manifest != other_manifest:
        raise RuntimeError('The two shells have different content manifests; one payload cannot be shared')
    print(f'  both shells: PRODUCT={first_info["PRODUCT"]} CHAIN={first_info["CHAIN"]} '
          f'SHADER_SRC={first_info["SHADER_SRC"]}, identical manifest')

    sources = {path: source_file(repo, commit, path) for path in SOURCE_FILES}
    product = sources['dm/PRODUCT'].strip()
    if first_info['PRODUCT'] != product:
        raise RuntimeError(f"shell PRODUCT {first_info['PRODUCT']} != dm/PRODUCT {product} at {commit[:12]}")
    names = re.search(r'static const char \*need\[\] = \{(.*?)\};', sources['dm/host/romfs_validate.c'], re.S)
    sizes = re.search(r'static const long long size\[\] = \{(.*?)\};', sources['dm/host/romfs_validate.c'], re.S)
    counts = (len(re.findall(r'"([^"]+\.data)"', names.group(1))), len(re.findall(r'\d+', sizes.group(1))))
    if counts != (18, 18):
        raise RuntimeError(f'romfs_validate.c no longer lists 18 files and 18 sizes: {counts}')
    rules = len(re.findall(r'^FILES\s*=', sources['dm/gfx/tools/dmsh_chain.py'], re.M))
    if rules != 1:
        raise RuntimeError(f'dmsh_chain.py declares {rules} FILES assignments; the shader cache key assumes one')
    print(f'  source: PRODUCT={product}, 18 resource archives, 1 shader rule set')

    return {'upstream_commit': commit, 'shell_sha256': digests[SHELL_ASSETS[0]],
            'ios18_shell_sha256': digests[SHELL_ASSETS[1]], 'game_version': product.split('-', 1)[0]}


def rewrite(path, replacements, dry_run):
    text = original = path.read_text()
    for old, new in replacements:
        text = text.replace(old, new)
    if text == original:
        return False
    if not dry_run:
        path.write_text(text)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('tag', nargs='?', help='upstream release tag (default: the latest release)')
    parser.add_argument('--check', action='store_true', help='verify the current pin and change nothing')
    parser.add_argument('--dry-run', action='store_true', help='report what would change, write nothing')
    parser.add_argument('--accept-unverified-hashes', action='store_true',
                        help='pin locally computed hashes when the release publishes no SHA256SUMS.txt')
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text())
    repo = config['upstream_repository']
    old_tag = ci.upstream_version()
    tag = args.tag or api(f'repos/{repo}/releases/latest')['tag_name']
    if not re.fullmatch(r'v?\d+\.\d+(\.\d+)?', tag):
        raise SystemExit(f'Unusual release tag {tag!r}; pass the tag explicitly if this is intentional.')
    if args.check:
        if args.tag and args.tag != old_tag:
            raise SystemExit(f'--check re-verifies the pinned release ({old_tag}); drop the tag argument')
        tag = old_tag
    print(f'Upstream {repo}: {old_tag} -> {tag}')

    with tempfile.TemporaryDirectory() as temp:
        pin = verify(repo, tag, Path(temp),
                     require_official=not (args.check or args.accept_unverified_hashes))

    if args.check:
        for key in ('upstream_commit', 'shell_sha256', 'ios18_shell_sha256'):
            state = 'OK  ' if config[key] == pin[key] else 'DRIFT'
            print(f'  {state} {key}: pinned {config[key]}')
        if config['game_version'] != pin['game_version']:
            print(f"  DRIFT game_version: config {config['game_version']} != shell {pin['game_version']}")
        return 0

    base = f'https://github.com/{repo}/releases/download/{tag}/'
    changes = {
        'upstream_commit': pin['upstream_commit'],
        'shell_url': base + SHELL_ASSETS[0],
        'shell_sha256': pin['shell_sha256'],
        'ios18_shell_url': base + SHELL_ASSETS[1],
        'ios18_shell_sha256': pin['ios18_shell_sha256'],
    }
    if config['game_version'] != pin['game_version']:
        changes['game_version'] = pin['game_version']
    changed = {k: (config.get(k), v) for k, v in changes.items() if config.get(k) != v}
    for key, (before, after) in changed.items():
        print(f'  build-config.json {key}:\n    - {before}\n    + {after}')
    if not changed:
        print('  build-config.json is already pinned to this release')

    docs = [ROOT / name for name in README_NAMES]
    doc_hits = []
    if tag != old_tag:
        for path in docs:
            text = path.read_text()
            if old_tag in text:
                doc_hits.append((path, old_tag, tag))
                print(f'  {path.name}: {text.count(old_tag)} reference(s) to {old_tag} -> {tag}')

    if args.dry_run:
        print('\nDry run: nothing written.')
        return 0

    if changes.get('game_version'):
        print(f"\n  NOTE: the game version moved to {changes['game_version']}. The published Data no longer\n"
              '  matches, so the next build must regenerate and re-upload the resource archives.')
    else:
        print(f"\n  Game version unchanged ({pin['game_version']}): the published Data is reused, "
              'nothing is re-uploaded.')

    updated = dict(config)
    updated.update(changes)
    CONFIG_PATH.write_text(json.dumps(updated, indent=2) + '\n')
    for path, old, new in doc_hits:
        rewrite(path, [(old, new)], False)
    print(f'\nWrote {CONFIG_PATH.relative_to(ROOT)} and {len(doc_hits)} README(s).')

    print('\nVerifying the tree:')
    tests = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'],
                           cwd=ROOT, capture_output=True, text=True)
    print('  ' + (tests.stderr.strip().splitlines() or ['no output'])[-1])
    if tests.returncode:
        print(tests.stdout[-2000:], file=sys.stderr)
        print('Tests failed; fix the tree before committing.', file=sys.stderr)
        return 1
    print('\nNext:\n'
          f'  git add -A && git commit -m "Update pinned upstream to {tag}"\n'
          '  git push\n'
          '  then run the "Build D2R Mobile IPA" workflow with publish_release enabled.\n'
          f'  If the game version moved, set input_revision to game-{pin["game_version"]}-v1 first.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeError as exc:
        # Every verification failure lands here as a plain reason, not a traceback.
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(2)
