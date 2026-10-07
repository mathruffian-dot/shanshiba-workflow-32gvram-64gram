"""Resumable ranged downloads from pinned official sources, with integrity checks.

Usage:  python download.py downloads_xxx.json   (run from anywhere; relative manifest paths resolve against this folder)

Every file in the manifest is downloaded (any extension). Verification per file:
  - "sha256" present  -> SHA-256 of the whole file must match (Hugging Face LFS files)
  - else "git_oid"    -> git blob SHA-1 must match (small non-LFS files on Hugging Face)
  - else              -> size must match
Files that already exist and verify are skipped, so re-running is safe. Large files are fetched in 8 MB ranges by
24 parallel connections (resumable); the temporary <file>.parts folder is deleted after verification.
Exit code is non-zero if any file fails."""
import concurrent.futures as cf
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
arg = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'downloads.json'
manifest = arg if arg.exists() else ROOT / arg
items = json.loads(manifest.read_text(encoding='utf-8-sig'))
CHUNK = 8 * 1024 * 1024
UA = {'User-Agent': 'H3-local-setup/1.1'}


def verify(path, item):
    """Return True if the file on disk matches the manifest entry."""
    if not path.exists() or path.stat().st_size != item['size']:
        return False
    if item.get('sha256'):
        h = hashlib.sha256()
        with path.open('rb') as f:
            while data := f.read(8 * 1024 * 1024):
                h.update(data)
        return h.hexdigest() == item['sha256']
    if item.get('git_oid'):
        h = hashlib.sha1(b'blob %d\0' % item['size'])
        h.update(path.read_bytes())
        return h.hexdigest() == item['git_oid']
    return True


def fetch(url, start=None, end=None):
    headers = dict(UA)
    if start is not None:
        headers['Range'] = f'bytes={start}-{end}'
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as r:
                if start is not None and (r.status != 206 or not r.headers.get('Content-Range', '').startswith(f'bytes {start}-{end}/')):
                    raise RuntimeError('Server did not honor exact range')
                return r.read()
        except Exception:
            if attempt == 7:
                raise
            time.sleep(min(2 ** attempt, 20))


def download(item):
    dest = Path(item['destination'])
    if verify(dest, item):
        return 'present'
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name + '.verified-tmp')
    if item['size'] <= CHUNK:                                  # small file: one request
        data = fetch(item['url']) if item['size'] else b''
        if len(data) != item['size']:
            raise RuntimeError(f"size mismatch: {item['name']} ({len(data)} != {item['size']})")
        temp.write_bytes(data)
    else:                                                       # large file: parallel ranges, resumable
        parts = dest.with_name(dest.name + '.parts')
        parts.mkdir(exist_ok=True)
        n = (item['size'] + CHUNK - 1) // CHUNK

        def part(i):
            start = i * CHUNK
            end = min(item['size'], start + CHUNK) - 1
            p = parts / str(i)
            if p.exists() and p.stat().st_size == end - start + 1:
                return
            data = fetch(item['url'], start, end)
            if len(data) != end - start + 1:
                raise RuntimeError('Incomplete range')
            p.write_bytes(data)
        begin = time.time()
        with cf.ThreadPoolExecutor(max_workers=24) as pool:
            futures = [pool.submit(part, i) for i in range(n)]
            for k, f in enumerate(cf.as_completed(futures), 1):
                f.result()
                if k % 32 == 0 or k == n:
                    print(f"{item['name']}: {k}/{n} chunks, {time.time() - begin:.0f}s", flush=True)
        with temp.open('wb') as out:
            for i in range(n):
                with (parts / str(i)).open('rb') as inp:
                    shutil.copyfileobj(inp, out, 4 * 1024 * 1024)
    if not verify(temp, item):
        temp.unlink(missing_ok=True)
        raise RuntimeError(f"verification failed: {item['name']}")
    os.replace(temp, dest)
    shutil.rmtree(dest.with_name(dest.name + '.parts'), ignore_errors=True)
    print(f"VERIFIED {dest}", flush=True)
    return 'downloaded'


counts = {'present': 0, 'downloaded': 0, 'failed': 0}
with cf.ThreadPoolExecutor(max_workers=5) as pool:
    futs = {pool.submit(download, item): item for item in items}
    for f in cf.as_completed(futs):
        try:
            counts[f.result()] += 1
        except Exception as e:
            counts['failed'] += 1
            print(f"FAILED {futs[f]['name']}: {e}", flush=True)
print(f"{manifest.name}: {len(items)} files — downloaded {counts['downloaded']}, already present {counts['present']}, failed {counts['failed']}", flush=True)
if counts['failed'] or counts['downloaded'] + counts['present'] != len(items):
    sys.exit(1)
print('ALL DOWNLOADS VERIFIED', flush=True)
