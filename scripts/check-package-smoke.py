"""Inspect a final release archive and start its bundled server with disposable data."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile


def file_hash(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_archive(path: Path) -> None:
    expected = path.with_name(path.name + '.sha256.txt').read_text().split()[0]
    if file_hash(path) != expected:
        raise ValueError(f'Archive checksum mismatch: {path.name}')
    if path.suffix == '.zip':
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.startswith(('/', '\\')) or '..' in name.replace('\\', '/').split('/') or ':' in name:
                    raise ValueError('Unsafe archive member')
            if archive.testzip():
                raise ValueError('Corrupt ZIP member')


@contextmanager
def unpack(path: Path, work: Path):
    destination = work / 'unpacked'
    destination.mkdir()
    if path.suffix == '.dmg':
        subprocess.run(['hdiutil', 'attach', str(path), '-readonly', '-nobrowse',
                        '-mountpoint', str(destination)], check=True, stdout=subprocess.DEVNULL)
        try:
            yield destination
        finally:
            subprocess.run(['hdiutil', 'detach', str(destination)], check=True, stdout=subprocess.DEVNULL)
    else:
        if sys.platform == 'darwin':
            subprocess.run(['ditto', '-x', '-k', str(path), str(destination)], check=True)
        else:
            with zipfile.ZipFile(path) as archive:
                archive.extractall(destination)
        yield destination


def smoke(root: Path, work: Path, *, kind: str, version: str, arch: str, python_version: str) -> dict:
    module = 'standard_webui_app' if kind == 'standard' else 'portable_webui_app'
    entries = list(root.rglob(module + '.py'))
    if len(entries) != 1:
        raise ValueError(f'Expected one packaged {module}, found {len(entries)}')
    app = entries[0].parent
    runtime = app.parent / 'python'
    marker = app.parent / ('app-version.txt' if kind == 'standard' else 'portable-version.txt')
    if marker.read_text().strip() != version:
        raise ValueError('Packaged version marker mismatch')
    python = (runtime / 'python.exe' if sys.platform == 'win32' else
              runtime / 'Python.framework/Versions/Current/bin/python3')
    if not python.is_file():
        raise ValueError('Packaged interpreter is missing')
    env = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE'):
        env.pop(key, None)
    env.update(PYTHONPATH=os.pathsep.join([str(app), str(app / '.deps')]),
               PYTHONDONTWRITEBYTECODE='1', ILAB_CONJURE_DATA_DIR=str(work / 'data'),
               CODEX_HOME=str(work / 'codex'), HOME=str(work / 'home'),
               USERPROFILE=str(work / 'home'), APPDATA=str(work / 'home'),
               ILAB_CONJURE_APP_DIR=str(app),
               APP_LAUNCHER_MODE='standard' if kind == 'standard' else 'portable')
    env.pop('ILAB_CONJURE_BUNDLE_DIR', None)
    if kind == 'portable':
        env['ILAB_CONJURE_BUNDLE_DIR'] = str(app.parent)
    probe = """
import importlib.util, io, json, platform, ssl
from importlib.metadata import version
from PIL import Image, ImageOps
import certifi
from codex_image.version import APP_VERSION
assert importlib.util.find_spec('pip') is None, 'Build-only pip remains in package'
ssl.create_default_context(cafile=certifi.where())
image = Image.new('RGB', (32, 24), 'green')
for fmt in ('PNG', 'JPEG', 'WEBP'):
    data = io.BytesIO(); image.save(data, format=fmt); data.seek(0)
    with Image.open(data) as decoded:
        thumb = ImageOps.exif_transpose(decoded); thumb.thumbnail((16, 16))
        assert thumb.size == (16, 12)
print(json.dumps({'python': platform.python_version(), 'arch': platform.machine(), 'app': APP_VERSION,
                  'Pillow': version('Pillow'), 'certifi': version('certifi')}))
"""
    inventory = json.loads(subprocess.check_output([str(python), '-c', probe], cwd=app, env=env, text=True))
    expected_arch = {'arm64': {'arm64', 'aarch64'}, 'x64': {'x86_64', 'amd64'}}[arch]
    if inventory['python'] != python_version or inventory['arch'].lower() not in expected_arch:
        raise ValueError(f'Unexpected packaged interpreter: {inventory}')
    if not version.startswith('dev-') and inventory['app'] != version:
        raise ValueError('Packaged source version differs from the release version')
    subprocess.run([str(python), str(app / 'codex_image/runtime_security.py'), '--runtime'],
                   cwd=app, env=env, check=True, timeout=30)
    subprocess.run([str(python), '-m', 'codex_image.dependency_check', '--requirements',
                    str(app / 'requirements-webui.txt')], cwd=app, env=env, check=True, timeout=30)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with (work / 'server.log').open('w+') as log:
        process = subprocess.Popen([str(python), '-m', 'codex_image.webui.server', f'{module}:app',
                                    '--host', '127.0.0.1', '--port', str(port), '--no-access-log'],
                                   cwd=app, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 45
            while True:
                if process.poll() is not None or time.monotonic() > deadline:
                    log.seek(0)
                    raise RuntimeError('Packaged server failed: ' + log.read()[-4000:])
                try:
                    with opener.open(f'http://127.0.0.1:{port}/api/health', timeout=1) as response:
                        if json.load(response).get('ok') is True:
                            break
                except OSError:
                    pass
                time.sleep(.2)
            for route in ('/', '/api/app-version', '/api/generation-catalog', '/static/app.js', '/static/styles.css'):
                with opener.open(f'http://127.0.0.1:{port}{route}', timeout=10) as response:
                    data = response.read()
                    if not data:
                        raise ValueError(f'Empty packaged response: {route}')
                    expected_version = inventory['app'] if version.startswith('dev-') else version
                    if route == '/api/app-version' and json.loads(data)['current_version'] != expected_version:
                        raise ValueError('Packaged application version mismatch')
                    if route == '/api/generation-catalog' and not json.loads(data).get('models'):
                        raise ValueError('Packaged model catalog is empty')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--kind', choices=['standard', 'portable'], required=True)
    parser.add_argument('--arch', choices=['arm64', 'x64'], required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--python-version', default='3.14.10')
    args = parser.parse_args()
    archives = sorted(p for p in args.directory.iterdir() if p.suffix in ('.zip', '.dmg'))
    if len(archives) != 1:
        raise SystemExit('Expected exactly one final archive')
    archive = archives[0].resolve()
    verify_archive(archive)
    with tempfile.TemporaryDirectory(prefix='conjure-package-smoke-') as temporary:
        work = Path(temporary)
        with unpack(archive, work) as root:
            inventory = smoke(root, work, kind=args.kind, version=args.version, arch=args.arch,
                              python_version=args.python_version)
    print(json.dumps({'archive': archive.name, 'passed': True, 'runtime': inventory}))


if __name__ == '__main__':
    main()
