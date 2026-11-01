"""Prepare verified release files, then publish only a complete GitHub draft."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess


def extract_notes(text: str, version: str) -> str:
    # Preserve Markdown headings; do not depend on the old “本版详情” sentinel.
    if '## 版本说明' in text:
        text = text.split('## 版本说明', 1)[1]
    text = re.split(r'^## (?:推荐下载|免安装一键包|应用包下载)\s*$', text, maxsplit=1, flags=re.M)[0].strip()
    if not re.search(rf'(?<![\w.])v{re.escape(version)}(?![\w.])', text):
        raise ValueError('Release notes must name the exact release version')
    if '草稿' in text or '尚未发布' in text:
        raise ValueError('Release notes are still marked as a draft')
    if not re.search(r'^[-*] ', text, re.M):
        raise ValueError('Release notes contain no change entries')
    return text + '\n'


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def gh(*args: str) -> str:
    return subprocess.run(['gh', *args], check=True, text=True, capture_output=True).stdout


def verify_tag(repo: str, tag: str, commit: str) -> None:
    target = json.loads(gh('api', f'repos/{repo}/git/ref/tags/{tag}'))['object']
    for _ in range(8):
        if target['type'] == 'commit':
            if target['sha'] != commit:
                raise ValueError('Release tag no longer points at the verified CI commit')
            return
        if target['type'] != 'tag':
            break
        target = json.loads(gh('api', f"repos/{repo}/git/tags/{target['sha']}"))['object']
    raise ValueError('Unable to resolve release tag to a commit')


def find_release(repo: str, tag: str) -> dict | None:
    # List is read-only and fails on network/auth errors instead of treating them as “not found”.
    pages = json.loads(gh('api', '--paginate', '--slurp', f'repos/{repo}/releases?per_page=100'))
    matches = [r for page in pages for r in page if r['tag_name'] == tag]
    if len(matches) > 1:
        raise ValueError('Multiple releases match the requested tag')
    return matches[0] if matches else None


def publish(*, repo: str, tag: str, commit: str, files: list[Path], notes: Path) -> None:
    verify_tag(repo, tag, commit)
    existing = find_release(repo, tag)
    if existing and not existing['draft']:
        raise ValueError('Refusing to overwrite an already published release')
    if existing is None:
        # A timeout must stop this run. A later explicit rerun first reconciles the existing draft.
        gh('release', 'create', tag, '--repo', repo, '--draft', '--verify-tag',
           '--target', commit, '--title', tag, '--notes-file', str(notes))
        existing = find_release(repo, tag)
        if existing is None:
            raise ValueError('Created draft could not be located; refusing to recreate it')
    else:
        gh('release', 'edit', tag, '--repo', repo, '--title', tag, '--notes-file', str(notes))
    # GitHub's tag endpoint returns published releases only. Keep the draft's
    # stable numeric identity for verification before and after publication.
    release_path = f"repos/{repo}/releases/{existing['id']}"
    gh('release', 'upload', tag, '--repo', repo, *(str(p) for p in files), '--clobber')
    release = json.loads(gh('api', release_path))
    if not release['draft'] or release['tag_name'] != tag:
        raise ValueError('Release state changed during upload')
    remote = json.loads(gh('api', f"repos/{repo}/releases/{release['id']}/assets?per_page=100"))
    expected = {p.name: p for p in files}
    if len(remote) != len(expected) or {a['name'] for a in remote} != set(expected):
        raise ValueError('Draft asset inventory is incomplete or contains unexpected files')
    for asset in remote:
        path = expected[asset['name']]
        if (asset['state'] != 'uploaded' or asset['size'] != path.stat().st_size
                or asset.get('digest') != 'sha256:' + digest(path)):
            raise ValueError(f"Draft asset verification failed: {path.name}")
    # Publish is the final write. Failure at any earlier step leaves a draft.
    verify_tag(repo, tag, commit)
    gh('release', 'edit', tag, '--repo', repo, '--draft=false')
    final = json.loads(gh('api', release_path))
    if final['draft'] or final.get('prerelease') or final['tag_name'] != tag:
        raise ValueError('Release publication was not confirmed')


def prepare(*, directory: Path, repo: str, tag: str, notes_source: Path, notes: Path) -> list[Path]:
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise ValueError('Expected vMAJOR.MINOR.PATCH')
    version = tag[1:]
    notes.write_text(extract_notes(notes_source.read_text(encoding='utf-8'), version), encoding='utf-8')
    spec = importlib.util.spec_from_file_location('update_manifest', Path(__file__).with_name('build-update-manifest.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = module.build_manifest(assets_dir=directory, version=version, tag=tag, repo=repo,
                                     notes=notes.read_text(encoding='utf-8'))
    downloads = ['\n## 下载 / Downloads\n']
    for group in ('standard_platforms', 'platforms'):
        for entry in manifest[group].values():
            downloads.append(f"- [{entry['asset']}]({entry['url']})\n")
    downloads.append(f'\n[完整说明 / Full release notes](https://github.com/{repo}/blob/{tag}/RELEASES.md)\n')
    manifest['notes'] += ''.join(downloads)
    notes.write_text(manifest['notes'], encoding='utf-8')
    packages = []
    for key in ('platforms', 'standard_platforms'):
        for entry in manifest[key].values():
            name = entry['asset']
            if not name.endswith((f'_{version}.zip', f'-{version}.dmg')):
                raise ValueError(f'Asset version mismatch: {name}')
            matches = list(directory.rglob(name))
            if len(matches) != 1:
                raise ValueError(f'Ambiguous asset: {name}')
            packages.extend([matches[0], matches[0].with_name(name + '.sha256.txt')])
    archives = {p for p in directory.rglob('*') if p.suffix in ('.zip', '.dmg')}
    if archives != {p for p in packages if p.suffix in ('.zip', '.dmg')}:
        raise ValueError('Unexpected archive in release artifacts')
    secret = os.environ.get('ILAB_CONJURE_UPDATE_SIGNING_PRIVATE_KEY_B64', '')
    if not secret:
        raise ValueError('Release signing key is missing')
    manifest['signature'] = module.sign_manifest(manifest, secret)
    manifest['standard_signature'] = module.sign_standard_manifest(manifest, secret)
    manifest_path = directory / 'latest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return [*packages, manifest_path]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets-dir', type=Path, required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--notes-source', type=Path, default=Path('RELEASES.md'))
    args = parser.parse_args()
    notes = args.assets_dir / 'release-notes.md'
    files = prepare(directory=args.assets_dir, repo=args.repo, tag=args.tag,
                    notes_source=args.notes_source, notes=notes)
    publish(repo=args.repo, tag=args.tag, commit=args.commit, files=files, notes=notes)


if __name__ == '__main__':
    main()
