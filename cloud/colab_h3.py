"""Run MiniMax H3 (and, if you have no usable GPU, the whole pipeline) on Google Colab from your own computer.
Everything stays on your disk: first frames / voices are uploaded, finished clips are downloaded, the Colab VM is wiped when it stops.
Needs: the Colab CLI (uv tool install google-colab-cli; Windows also: python cloud/colab_cli_windows_patch.py), `colab usage` signed in
once with the Google account that has the Google AI plan (or Colab pay-as-you-go compute units). Standard library only.

  python cloud/colab_h3.py check                       # CLI works? balance? which GPUs?
  python cloud/colab_h3.py start                       # DEFAULT = full install, same as the full 32G repo (voice, Qwen, Music 3, H3, FlashVSR; ~10.5 min)
  python cloud/colab_h3.py start --h3-only             # only ComfyUI + H3 (~3.7 min), 2 ComfyUI instances: local prep + cloud H3, or hybrid
  python cloud/colab_h3.py batch a/spec.json b/spec.json ...   # upload -> render on the VM -> download clips next to each spec
  python cloud/colab_h3.py keepalive --minutes 30      # keep the VM while you review (Colab reclaims it after ~20 min idle)
  python cloud/colab_h3.py stop                        # always stop when done - an idle G4 still costs 8.9 units/hour
  python cloud/colab_h3.py full-setup                  # same as the default start (kept as an alias)
  python cloud/colab_h3.py smoke                       # after the full install: run setup/smoke_test.py on the VM, download smoke_out/
  python cloud/colab_h3.py film pipeline/template_local [stage ...]   # after the full install: run make_film.py on the VM, sync out/ back
  python cloud/hybrid_h3.py out/h3/S01 out/h3/S02 ...  # local GPU + Colab together (measured 2026-10-11: 34 shots 17.9 min vs 32.6 min local)

Measured 2026-10-10 (Colab, Google AI Pro): G4 = RTX PRO 6000 Blackwell 96 GB, 8.90 compute units/hour; one 90-frame DMAD shot 42 s
with models kept loaded; 2 staggered instances = 123 shots/hour (0.073 units/shot). L4 / A100 are slower AND cost more units per shot.
G4 machines were always in the USA or the EU (Netherlands) - both are excluded territories in the MiniMax H3 licence: decide yourself."""
import argparse, json, os, re, shutil, subprocess, sys, tarfile, tempfile, time, zipfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO = Path(__file__).resolve().parents[1]
EXCLUDED = {"US", "GB", "KR", "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT",
            "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}     # MiniMax H3 licence I.5: US, EU, UK, Republic of Korea
FILE_KEYS = ["first_frame", "last_frame", "first_clip"]
RETRY = ("Connection was lost", "Timeout waiting for reply", "Read timed out", "ConnectionError", "RemoteDisconnected")


def colab_bin():
    b = shutil.which("colab")
    if not b:
        sys.exit("找不到 colab 指令：先執行  uv tool install google-colab-cli  （Windows 再執行 python cloud/colab_cli_windows_patch.py）")
    return b


def cx(args, inp=None, timeout=900, tries=4, check=True):
    """Run a colab CLI command with retries on the CLI's transient connection errors."""
    out = ""
    for k in range(tries):
        try:
            r = subprocess.run([colab_bin()] + [str(a) for a in args], input=inp, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            out = r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            out = "Timeout waiting for reply (local timeout)"
        if "termios" in out:
            sys.exit("Colab CLI 在 Windows 上壞掉（termios）：先執行  python cloud/colab_cli_windows_patch.py")
        if not any(m in out for m in RETRY):
            break
        time.sleep(5 * (k + 1))
    if check and "Session not found" in out:
        sys.exit("Colab 機器已經不在了（閒置約 20 分鐘會被收回）。重新執行 start。")
    return out


def vm(name, code, timeout=300):
    """Run Python code on the VM, return its printed output."""
    return cx(["exec", "-s", name], inp=code, timeout=timeout)


def vm_sh(name, cmd, timeout=300):
    return vm(name, f"import subprocess\nr = subprocess.run({cmd!r}, shell=True, capture_output=True, text=True)\nprint(r.stdout[-6000:] + r.stderr[-3000:])",
              timeout)


def alive(name):
    return f"[{name}]" in cx(["sessions"], check=False)


def balance():
    m = re.search(r"Current balance:\s*([\d.]+)", cx(["usage"], check=False))
    return float(m.group(1)) if m else None


def upload(name, local, remote):
    out = cx(["upload", "-s", name, local, remote], timeout=1800)
    if "Uploaded" not in out:
        sys.exit(f"上傳失敗：{local}\n{out[-800:]}")


def download(name, remote, local):
    Path(local).parent.mkdir(parents=True, exist_ok=True)
    out = cx(["download", "-s", name, remote, local], timeout=3600)
    if "Downloaded" not in out:
        sys.exit(f"下載失敗：{remote}\n{out[-800:]}")


def repo_bundle(full=False):
    """tools/ + setup/ + cloud/vm/ (+ pipeline/templates/sfx for the full mode) as one tar.gz - one upload instead of hundreds."""
    tmp = Path(tempfile.mkdtemp()) / "repo.tgz"
    parts = ["tools", "setup", "cloud"] + (["pipeline", "templates", "sfx"] if full else [])
    with tarfile.open(tmp, "w:gz") as t:
        for p in parts:
            if (REPO / p).exists():
                t.add(REPO / p, arcname=p, filter=lambda ti: None if any(x in ti.name for x in ("/out/", "__pycache__", "smoke_out")) else ti)
    return tmp


def poll(name, logfile, done, fail=("FAILED",), every=60, limit=7200, show=r"^\[(setup|full)\]"):
    """Wait for a marker in a VM log, printing new progress lines. Polling also keeps the session from being reclaimed as idle."""
    seen, t0 = 0, time.time()
    while time.time() - t0 < limit:
        txt = vm(name, f"import os\nprint(open({logfile!r}, errors='replace').read() if os.path.exists({logfile!r}) else '')")
        lines = [l for l in txt.splitlines() if re.search(show, l) or any(f in l for f in fail) or done in l]
        for l in lines[seen:]:
            print("   ", l[:300], flush=True)
        seen = max(seen, len(lines))
        if done in txt:
            return txt
        # smoke_test step lines ("FAIL <step> ... Traceback ...") are results, not a crash of the script being watched
        if any(f in l for l in lines if not re.match(r"(OK|FAIL)\s", l) for f in fail):
            sys.exit(f"VM 上失敗了，看上面的訊息（完整記錄在 VM 的 {logfile}）")
        time.sleep(every)
    sys.exit(f"等太久（{limit // 60} 分鐘）還沒完成：{logfile}")


def new_session(name, gpu):
    if alive(name):
        return False
    print(f"[colab] 開一台 {gpu}（餘額 {balance()} 單元）…", flush=True)
    out = cx(["new", "-s", name, "--gpu", gpu], timeout=600)
    if "rejected" in out.lower() or "Session READY" not in out:
        sys.exit(f"開機失敗（這個帳號可能不能用 {gpu}）：\n{out[-600:]}")
    reg = vm(name, "import json, urllib.request\ntry:\n  d = json.loads(urllib.request.urlopen('https://ipinfo.io/json', timeout=15).read())\n"
                   "  print('REGION', d.get('country'), d.get('city'))\nexcept Exception as e:\n  print('REGION ?', e)")
    m = re.search(r"REGION (\S+) ?(.*)", reg)
    cc = m.group(1) if m else "?"
    print(f"[colab] 機房：{m.group(2).strip() if m else '?'}（{cc}）", flush=True)
    if cc in EXCLUDED:
        print("  ⚠ 這個機房在 MiniMax H3 授權排除的地區（美國／歐盟／英國／南韓）。授權沒有定義『使用』看人還是看機器；"
              "要不要在這裡跑 H3 由你自己評估、風險自負。替代：台灣或日本機房的雲端 GPU（見 cloud/README.md）。", flush=True)
    vm(name, "import os; os.makedirs('/content/repo', exist_ok=True); print('ok')")
    return True


def cmd_check(a):
    print(cx(["version"], check=False).strip())
    out = cx(["usage"], check=False)
    print(out.strip()[-400:])
    if "balance" not in out.lower():
        print("→ 還沒登入：在終端機執行  colab usage  ，瀏覽器選有 Google AI 方案的帳號，把授權碼貼回終端機。")


def cmd_start(a):
    """預設＝完整安裝（等同第一份 repo 完整版：語音、生圖、配樂、H3、放大全部裝，約 10.5 分鐘、約 1.5 單元；使用者 2026-10-11 指定）。
    --h3-only＝只裝 ComfyUI＋H3（約 3.7 分鐘），給「本機準備、雲端只跑 H3」與本機＋Colab 一起跑（hybrid_h3.py）用。"""
    if not getattr(a, "h3_only", False):
        return cmd_full_setup(a)
    fresh = new_session(a.name, a.gpu)
    if not fresh and "SETUP_DONE" in vm(a.name, "import os\nprint(open('/content/setup_h3.log').read() if os.path.exists('/content/setup_h3.log') else '')"):
        print("[colab] 已經準備好了（沿用這台）", flush=True)
        return
    t0 = time.time()
    tgz = repo_bundle()
    upload(a.name, tgz, "/content/repo.tgz")
    vm_sh(a.name, "cd /content/repo && tar xzf /content/repo.tgz && echo ok")
    vm_sh(a.name, f"cd /content && nohup python /content/repo/cloud/vm/setup_h3.py --instances {a.instances} --encoder {a.encoder} "
                  f"> /content/setup_h3.log 2>&1 &")
    poll(a.name, "/content/setup_h3.log", "SETUP_DONE", every=30)
    print(f"[colab] 可以開始跑 H3 了（{time.time() - t0:.0f} 秒）。用完記得 stop。", flush=True)


def files_in(spec):
    """(json path, value) for every asset path inside an h3_shot spec."""
    out = [((k,), spec[k]) for k in FILE_KEYS if isinstance(spec.get(k), str)]
    for k in ("fixed", "voice_ref"):
        if isinstance(spec.get("audio", {}).get(k), dict) and spec["audio"][k].get("file"):
            out.append((("audio", k, "file"), spec["audio"][k]["file"]))
    if isinstance(spec.get("camera_video"), dict) and spec["camera_video"].get("file"):
        out.append((("camera_video", "file"), spec["camera_video"]["file"]))
    for i, s in enumerate(spec.get("subjects", [])):
        if s.get("identity_image"):
            out.append((("subjects", i, "identity_image"), s["identity_image"]))
    ctl = spec.get("control")
    for i, c in enumerate(ctl if isinstance(ctl, list) else ([ctl] if isinstance(ctl, dict) else [])):
        if c.get("file"):
            out.append((("control", i, "file") if isinstance(ctl, list) else ("control", "file"), c["file"]))
    return out


def set_in(d, path, v):
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = v


def out_dir(spec_path):
    return spec_path.parent if spec_path.name == "spec.json" else spec_path.with_suffix("")


def cmd_batch(a):
    specs = [Path(s).resolve() for s in a.specs]
    if not alive(a.name) or "SETUP_DONE" not in vm(a.name, "import os\nprint(open('/content/setup_h3.log').read() if os.path.exists('/content/setup_h3.log') else '')"):
        cmd_start(a)
    batch = time.strftime("b%Y%m%d_%H%M%S")
    tmp = Path(tempfile.mkdtemp()); jobs = []; where = {}
    for n, sp in enumerate(specs):
        spec = json.loads(sp.read_text(encoding="utf-8"))
        jid = f"{n:03d}_" + re.sub(r"[^A-Za-z0-9_-]", "_", sp.parent.name if sp.name == "spec.json" else sp.stem)[:40]
        jd = tmp / batch / jid; jd.mkdir(parents=True)
        for k, (path, val) in enumerate(files_in(spec)):
            src = Path(val) if Path(val).is_absolute() else sp.parent / val
            if not src.exists():
                sys.exit(f"{sp}: 找不到 {val}")
            name = f"f{k}_{src.name}"
            shutil.copy2(src, jd / name); set_in(spec, path, name)
        (jd / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        jobs.append({"id": jid}); where[jid] = out_dir(sp)
    (tmp / batch / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    zp = tmp / f"{batch}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (tmp / batch).rglob("*"):
            z.write(f, f.relative_to(tmp).as_posix())
    print(f"[batch] {len(jobs)} 鏡，上傳 {zp.stat().st_size / 1e6:.1f} MB …", flush=True)
    vm_sh(a.name, "mkdir -p /content/jobs")
    upload(a.name, zp, f"/content/jobs/{batch}.zip")
    vm_sh(a.name, f"cd /content/jobs && python -c \"import zipfile; zipfile.ZipFile('{batch}.zip').extractall('.')\" && "
                  f"nohup python /content/repo/cloud/vm/run_batch.py {batch} > /content/jobs/{batch}.log 2>&1 &")
    t0 = time.time(); seen = 0
    while True:
        time.sleep(int(os.environ.get("COLAB_POLL", "15")))     # 2026-10-11 實測：45 秒輪詢每批多耗損約 30 秒 → 預設 15
        txt = vm(a.name, f"import os\np='/content/jobs/{batch}/progress.jsonl'\nprint(open(p).read() if os.path.exists(p) else '')\n"
                         f"l='/content/jobs/{batch}.log'\nprint('LOGTAIL', open(l).read()[-800:] if os.path.exists(l) else '')")
        ev = [json.loads(l) for l in txt.splitlines() if l.startswith("{")]
        for e in ev[seen:]:
            if e["event"] == "job":
                print(f"   {e['id']}: {'OK' if e['ok'] else 'FAIL'} {e['sec']} 秒" + ("" if e["ok"] else f"\n      {e['err'][-300:]}"), flush=True)
        seen = len(ev)
        if any(e["event"] == "DONE" for e in ev):
            break
        if "Traceback" in txt.split("LOGTAIL")[-1]:
            sys.exit("VM 上的批次程式出錯：\n" + txt.split("LOGTAIL")[-1])
    done = [e for e in ev if e["event"] == "job"]
    lz = tmp / f"{batch}_out.zip"
    download(a.name, f"/content/jobs/{batch}_out.zip", lz)
    with zipfile.ZipFile(lz) as z:
        for m in z.namelist():
            jid, rel = m.split("/", 1)
            dst = where[jid] / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(z.read(m))
    okn = sum(e["ok"] for e in done)
    print(f"[batch] 完成 {okn}/{len(jobs)} 鏡，{time.time() - t0:.0f} 秒；成品已存回各 spec 旁邊。餘額 {balance()} 單元。", flush=True)
    if a.stop_after:
        cmd_stop(a)
    if okn < len(jobs):
        sys.exit(1)


def cmd_keepalive(a):
    end = time.time() + a.minutes * 60
    print(f"[colab] 保持連線 {a.minutes} 分鐘（這段時間照樣扣單元；Ctrl+C 結束）", flush=True)
    while time.time() < end:
        vm(a.name, "print('ok')")
        time.sleep(240)


def cmd_stop(a):
    print(cx(["stop", "-s", a.name], check=False).strip()[-200:])
    print(f"[colab] 餘額 {balance()} 單元", flush=True)


def cmd_status(a):
    print(cx(["sessions"], check=False).strip())
    print(cx(["usage"], check=False).strip())


def cmd_full_setup(a):
    fresh = new_session(a.name, a.gpu)
    if not fresh and '"full": true' in vm(a.name, "import os\nprint(open('/content/h3_state.json').read() if os.path.exists('/content/h3_state.json') else '')"):
        print("[colab] 全套環境已經裝好了（沿用這台）", flush=True)
        return
    tgz = repo_bundle(full=True)
    upload(a.name, tgz, "/content/repo.tgz")
    vm_sh(a.name, "cd /content/repo && tar xzf /content/repo.tgz && echo ok")
    vm_sh(a.name, "cd /content && AI_ROOT=/content/AI REPO=/content/repo nohup bash /content/repo/cloud/vm/install_full.sh > /content/install_full.log 2>&1 &")
    poll(a.name, "/content/install_full.log", "FULL_DONE", every=60)
    vm_sh(a.name, "echo SETUP_DONE >> /content/setup_h3.log")      # batch/film can reuse this VM
    print("[colab] 全套環境裝好了（之後可以用 smoke／film／batch）", flush=True)


VM_ENV = ("AI_ROOT=/content/AI AI_TOOLS=/content/repo/tools PY_H3=python PY_VOICE=/content/AI/Voice/venv/bin/python "
          "PY_BREEZE=/content/AI/BreezeTTS/venv/bin/python PY_BREEZYVOICE=/content/AI/BreezyVoice/venv/bin/python "
          "COMFY_DIR=/content/AI/H3/ComfyUI-0.36.0 H3_BACKEND=local UPSCALE=lanczos H3_PARALLEL=2")


def cmd_smoke(a):
    vm_sh(a.name, f"cd /content/repo/setup && {VM_ENV} nohup python smoke_test.py > /content/smoke.log 2>&1 &")
    poll(a.name, "/content/smoke.log", "Watch setup/smoke_out", fail=("Traceback",), every=60, show=r"^(OK|FAIL) |ALL OK|FAILED:")
    vm_sh(a.name, "cd /content/repo/setup && rm -f smoke_out.zip && python -c \"import shutil; shutil.make_archive('smoke_out', 'zip', 'smoke_out')\"")
    dst = REPO / "setup" / "smoke_out_colab"
    download(a.name, "/content/repo/setup/smoke_out.zip", dst / "smoke_out.zip")
    zipfile.ZipFile(dst / "smoke_out.zip").extractall(dst)
    print(f"[smoke] 結果在 {dst}（report.json、h3/clip.mp4…）", flush=True)


def cmd_film(a):
    """Full-cloud make_film.py: upload the film folder (film.json + out/), run the given stages on the VM, bring out/ back."""
    fd = Path(a.film_dir).resolve()
    rel = fd.relative_to(REPO).as_posix()
    # 本機設的 ONLY／ALLOW_REVIEW／UPSCALE 也帶到 VM（make_film.py 用它們重做指定鏡頭、放行審查）；--env KEY=VALUE 可再加
    extra = [f"{k}={os.environ[k]}" for k in ("ONLY", "ALLOW_REVIEW", "UPSCALE") if os.environ.get(k)] + list(a.env)
    for kv in extra:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=[^'\"]*", kv):
            sys.exit(f"--env 格式要 KEY=VALUE（不能有引號）：{kv}")
    env = VM_ENV + "".join(f" {k}='{v}'" for k, v in (kv.split("=", 1) for kv in extra))
    if extra:
        print(f"[film] 帶到 VM 的設定：{' '.join(extra)}", flush=True)
    tmp = Path(tempfile.mkdtemp()) / "film.zip"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in fd.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(fd).as_posix())
    print(f"[film] 上傳 {rel}（{tmp.stat().st_size / 1e6:.1f} MB）…", flush=True)
    upload(a.name, tmp, "/content/film.zip")
    vm_sh(a.name, f"mkdir -p /content/repo/{rel} && cd /content/repo/{rel} && python -c \"import zipfile; zipfile.ZipFile('/content/film.zip').extractall('.')\""
                  f" && nohup sh -c 'env {env.replace("'", "'" + chr(92) + "''")} python make_film.py {' '.join(a.stages)} > /content/film.log 2>&1; echo FILM_EXIT $? >> /content/film.log'"
                  f" > /dev/null 2>&1 &")
    poll(a.name, "/content/film.log", "FILM_EXIT", fail=("FAILED:", "Traceback"), every=60, show=r"^\[stage\]|^→|成片|FILM_EXIT")
    vm_sh(a.name, f"cd /content/repo/{rel} && rm -f /content/film_out.zip && python -c \"import shutil; shutil.make_archive('/content/film_out', 'zip', 'out')\"")
    lz = Path(tempfile.mkdtemp()) / "film_out.zip"
    download(a.name, "/content/film_out.zip", lz)
    zipfile.ZipFile(lz).extractall(fd / "out")
    print(f"[film] out/ 已同步回 {fd / 'out'}；人工檢查後再跑下一段 stage。", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="h3", help="Colab session name (default h3)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    for c in ("start", "batch", "full-setup"):
        p = sub.add_parser(c)
        p.add_argument("--gpu", default="G4", help="G4 (default, fastest AND cheapest per shot) | A100 | L4")
        if c in ("start", "batch"):
            p.add_argument("--h3-only", action="store_true",
                           help="only ComfyUI+H3 (~3.7 min) instead of the default full install (~10.5 min, same as the full 32G repo)")
        if c != "full-setup":
            p.add_argument("--instances", type=int, default=2, help="ComfyUI instances on the VM (2 = best throughput on G4)")
            p.add_argument("--encoder", default="heretic", choices=["heretic", "nvfp4"])
        if c == "batch":
            p.add_argument("specs", nargs="+", help="h3_shot spec files (outputs go next to each: <dir>/ for spec.json, else <name>/)")
            p.add_argument("--stop-after", action="store_true", help="stop the VM when the batch is downloaded")
    sub.add_parser("keepalive").add_argument("--minutes", type=int, default=30)
    sub.add_parser("stop"); sub.add_parser("status"); sub.add_parser("smoke")
    p = sub.add_parser("film"); p.add_argument("film_dir"); p.add_argument("stages", nargs="*")
    p.add_argument("--env", action="append", default=[], help="extra KEY=VALUE for make_film.py on the VM (e.g. ONLY=S3); ONLY/ALLOW_REVIEW/UPSCALE set locally are passed automatically")
    a = ap.parse_args()
    {"check": cmd_check, "start": cmd_start, "batch": cmd_batch, "keepalive": cmd_keepalive, "stop": cmd_stop, "status": cmd_status,
     "full-setup": cmd_full_setup, "smoke": cmd_smoke, "film": cmd_film}[a.cmd](a)


if __name__ == "__main__":
    main()
