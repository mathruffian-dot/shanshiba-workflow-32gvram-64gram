"""Resumable ranged downloads from pinned official sources, with integrity checks.

Usage:  python download.py downloads_xxx.json   (run from anywhere; relative manifest paths resolve against this folder)

Every file in the manifest is downloaded (any extension). Verification per file:
  - "sha256" present  -> SHA-256 of the whole file must match (Hugging Face LFS files)
  - else "git_oid"    -> git blob SHA-1 must match (small non-LFS files on Hugging Face)
  - else              -> size must match
Files that already exist and verify are skipped, so re-running is safe. Large files: the Hugging Face redirect is
resolved once, then 16 long ranged streams write straight into <file>.verified-tmp (no extra disk copy); progress is
kept in <file>.progress.json so an interrupted download resumes. HTTP 429 / 5xx are retried with backoff.
(2026-10-10: the old 8 MB-per-request scheme sent ~3,000 requests per 26 GB file to huggingface.co and got
HTTP 429 Too Many Requests when several manifests ran at once on Colab.)
Set AI_ROOT to install somewhere other than C:/AI (e.g. /content/AI on Colab/Linux); set HF_TOKEN for higher limits.
Exit code is non-zero if any file fails."""
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
arg = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'downloads.json'
manifest = arg if arg.exists() else ROOT / arg
items = json.loads(manifest.read_text(encoding='utf-8-sig'))
SMALL = 8 * 1024 * 1024       # files up to this size: one request
SEGMENTS = 16                 # long ranged streams per large file
READ = 4 * 1024 * 1024
UA = {'User-Agent': 'H3-local-setup/1.2'}
if os.environ.get('HF_TOKEN'):
    UA['Authorization'] = f"Bearer {os.environ['HF_TOKEN']}"
AI_ROOT = os.environ.get('AI_ROOT')                    # manifests are written for C:/AI; set AI_ROOT (e.g. /content/AI) to install elsewhere


def destination(item):
    d = item['destination'].replace('\\', '/')
    if AI_ROOT and d.startswith('C:/AI/'):
        return Path(AI_ROOT) / d[len('C:/AI/'):]
    return Path(d)


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


def backoff(attempt, err):
    """Seconds to wait before retrying; honours Retry-After on 429/503."""
    if isinstance(err, urllib.error.HTTPError) and err.code in (429, 503):
        try:
            return min(float(err.headers.get('Retry-After', 0)) or 30 * (attempt + 1), 300)
        except ValueError:
            return 30 * (attempt + 1)
    return min(2 ** attempt, 30)


def fetch(url):
    """Whole small file in one request."""
    for attempt in range(10):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read()
        except Exception as e:
            if attempt == 9:
                raise
            time.sleep(backoff(attempt, e))


def resolve(url):
    """Follow the Hugging Face redirect once; returns the CDN URL that serves the bytes."""
    for attempt in range(10):
        try:
            req = urllib.request.Request(url, headers={**UA, 'Range': 'bytes=0-0'})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.geturl()
        except Exception as e:
            if attempt == 9:
                raise
            time.sleep(backoff(attempt, e))


def download_large(item, temp):
    size = item['size']
    prog_path = temp.with_name(temp.name + '.progress.json')
    step = -(-size // SEGMENTS)
    segs = [(i * step, min(size, (i + 1) * step) - 1) for i in range(SEGMENTS) if i * step < size]
    done = json.loads(prog_path.read_text()) if prog_path.exists() and temp.exists() else {}
    if not temp.exists() or temp.stat().st_size != size:
        with temp.open('wb') as f:
            f.truncate(size)
        done = {}
    lock = threading.Lock()
    state = {'url': resolve(item['url']), 'last_save': time.time()}
    begin, base = time.time(), sum(done.values())

    def save():
        prog_path.write_text(json.dumps(done))

    def segment(i, start, end):
        for attempt in range(12):
            pos = start + done.get(str(i), 0)
            if pos > end:
                return
            try:
                req = urllib.request.Request(state['url'], headers={**UA, 'Range': f'bytes={pos}-{end}'})
                with urllib.request.urlopen(req, timeout=120) as r, temp.open('r+b') as f:
                    if r.status != 206:
                        raise RuntimeError('Server did not honor range')
                    f.seek(pos)
                    while chunk := r.read(READ):
                        f.write(chunk)
                        with lock:
                            done[str(i)] = done.get(str(i), 0) + len(chunk)
                            if time.time() - state['last_save'] > 5:
                                f.flush(); save(); state['last_save'] = time.time()
                if start + done.get(str(i), 0) > end:
                    return
            except Exception as e:
                if isinstance(e, urllib.error.HTTPError) and e.code in (403, 410):   # signed CDN URL expired
                    with lock:
                        state['url'] = resolve(item['url'])
                if attempt == 11:
                    raise
                time.sleep(backoff(attempt, e))
        raise RuntimeError(f'segment {i} incomplete')

    stop = threading.Event()

    def report():
        while not stop.wait(30):
            got = sum(done.values())
            print(f"{item['name']}: {got / 1e9:.1f}/{size / 1e9:.1f} GB, "
                  f"{(got - base) / 1e6 / max(time.time() - begin, 1):.0f} MB/s", flush=True)
    threading.Thread(target=report, daemon=True).start()
    try:
        with cf.ThreadPoolExecutor(max_workers=len(segs)) as pool:
            for f in [pool.submit(segment, i, s, e) for i, (s, e) in enumerate(segs)]:
                f.result()
    finally:
        stop.set()
        save()


def download(item):
    dest = destination(item)
    if verify(dest, item):
        return 'present'
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name + '.verified-tmp')
    if item['size'] <= SMALL:                                  # small file: one request
        data = fetch(item['url']) if item['size'] else b''
        if len(data) != item['size']:
            raise RuntimeError(f"size mismatch: {item['name']} ({len(data)} != {item['size']})")
        temp.write_bytes(data)
    else:                                                       # large file: 16 resumable streams into one file
        download_large(item, temp)
    if not verify(temp, item):
        temp.unlink(missing_ok=True)
        temp.with_name(temp.name + '.progress.json').unlink(missing_ok=True)
        raise RuntimeError(f"verification failed: {item['name']}")
    os.replace(temp, dest)
    temp.with_name(temp.name + '.progress.json').unlink(missing_ok=True)
    print(f"VERIFIED {dest}", flush=True)
    return 'downloaded'


counts = {'present': 0, 'downloaded': 0, 'failed': 0}
with cf.ThreadPoolExecutor(max_workers=4) as pool:
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
