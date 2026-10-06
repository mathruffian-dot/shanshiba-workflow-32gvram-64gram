"""Resumable ranged downloads from pinned official sources, with SHA-256 checks."""
import concurrent.futures as cf
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
import sys

ROOT = Path(__file__).parent
manifest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'downloads.json'
items = [x for x in json.loads(manifest.read_text(encoding='utf-8-sig')) if x['name'].endswith(('.safetensors', '.pth'))]
CHUNK = 8 * 1024 * 1024

def download(item):
    dest = Path(item['destination'])
    dest.parent.mkdir(parents=True, exist_ok=True)
    parts = dest.with_name(dest.name + '.parts')
    parts.mkdir(exist_ok=True)
    def part(i):
        start = i * CHUNK
        end = min(item['size'], start + CHUNK) - 1
        p = parts / str(i)
        if p.exists() and p.stat().st_size == end - start + 1:
            return
        for attempt in range(8):
            try:
                req = urllib.request.Request(item['url'], headers={'Range': f'bytes={start}-{end}', 'User-Agent': 'H3-local-setup/1.0'})
                with urllib.request.urlopen(req, timeout=90) as r:
                    if r.status != 206 or not r.headers.get('Content-Range', '').startswith(f'bytes {start}-{end}/'):
                        raise RuntimeError('Server did not honor exact range')
                    data = r.read()
                if len(data) != end-start+1:
                    raise RuntimeError('Incomplete range')
                p.write_bytes(data)
                return
            except Exception as e:
                if attempt == 7:
                    raise
                time.sleep(min(2**attempt, 20))
    n = (item['size'] + CHUNK - 1) // CHUNK
    begin = time.time()
    with cf.ThreadPoolExecutor(max_workers=24) as pool:
        futures = [pool.submit(part, i) for i in range(n)]
        for k, f in enumerate(cf.as_completed(futures), 1):
            f.result()
            if k % 32 == 0 or k == n:
                print(f"{item['name']}: {k}/{n} chunks, {time.time()-begin:.0f}s", flush=True)
    h = hashlib.sha256()
    temp = dest.with_name(dest.name + '.verified-tmp')
    with temp.open('wb') as out:
        for i in range(n):
            with (parts / str(i)).open('rb') as inp:
                while data := inp.read(4*1024*1024):
                    h.update(data)
                    out.write(data)
    if h.hexdigest() != item['sha256']:
        raise RuntimeError(f"SHA256 mismatch: {item['name']}")
    os.replace(temp, dest)
    print(f"VERIFIED {dest}", flush=True)

with cf.ThreadPoolExecutor(max_workers=5) as pool:
    for f in cf.as_completed([pool.submit(download, item) for item in items]):
        f.result()
print('ALL DOWNLOADS VERIFIED', flush=True)
