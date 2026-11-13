"""Run MiniMax H3 on a RunPod GPU pod from your own computer (same idea as cloud/colab_h3.py, for when Colab has no G4).
Rents a pod through the RunPod REST API, installs ComfyUI + H3 with the same cloud/vm/setup_h3.py as Colab, renders your
h3_shot specs there, downloads the clips next to each spec, and deletes the pod. Standard library + the ssh/scp/tar that ship
with Windows 10/11, macOS and Linux.

Needs: a RunPod account with credit and an API key whose REST "Pods" permission is Read/Write (GraphQL read-only is enough).
Put the key in the environment variable RUNPOD_API_KEY, or in a text file named by RUNPOD_KEY_FILE. Never paste it into a chat.

  python cloud/runpod_h3.py check                         # key works? balance? which of RTX 5090 / RTX PRO 6000 is in stock?
  python cloud/runpod_h3.py start --gpu 5090              # rent + install (about 4 min); --gpu pro6000 = 96 GB, 2 ComfyUI instances
  python cloud/runpod_h3.py batch a/spec.json b/spec.json  # upload -> render -> download clips next to each spec (starts a pod if none)
  python cloud/runpod_h3.py batch ... --stop-after         # ... and delete the pod at the end
  python cloud/runpod_h3.py status
  python cloud/runpod_h3.py stop                          # DELETE the pod (billing stops; models on it are gone)

Measured 2026-11-13 (models kept loaded, torch 2.14 cu130): 5 s DMAD shot = 70 s on RTX 5090 (US$1.39/h, Iceland),
59 s on RTX PRO 6000 Workstation (US$2.82/h, Romania); 5 s 14-step = 143 s / 135 s; output matches a local RTX 5090
(PSNR 42-43 dB, same seed). From "start" to the first shot: about 4 minutes (55 GB of models in 60-85 s).
RunPod pods can be anywhere; the MiniMax H3 licence excludes the US, the EU, the UK and the Republic of Korea - decide yourself."""
import argparse, json, os, subprocess, sys, tempfile, time, urllib.request, urllib.error, zipfile, re, shutil
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from colab_h3 import repo_bundle, files_in, set_in, out_dir, EXCLUDED     # same packaging as the Colab path

REST = "https://rest.runpod.io/v1"
GQL = "https://api.runpod.io/graphql"
STATE = Path.home() / ".shanshiba_runpod.json"
SSH_KEY = Path.home() / ".ssh" / "id_ed25519_runpod"
IMAGE = "runpod/pytorch:2.1.0-cu1281-torch280-ubuntu2404"
GPUS = {"5090": (["NVIDIA GeForce RTX 5090"], 1),
        "pro6000": (["NVIDIA RTX PRO 6000 Blackwell Server Edition", "NVIDIA RTX PRO 6000 Blackwell Workstation Edition"], 2)}
ENV = "export PIP_BREAK_SYSTEM_PACKAGES=1 UV_BREAK_SYSTEM_PACKAGES=1 AI_ROOT=/content/AI REPO=/content/repo; "


def key():
    k = os.environ.get("RUNPOD_API_KEY", "").strip()
    if not k and os.environ.get("RUNPOD_KEY_FILE"):
        k = Path(os.environ["RUNPOD_KEY_FILE"]).read_text(encoding="utf-8").strip()
    if not k:
        sys.exit("找不到 RunPod API 金鑰：設定環境變數 RUNPOD_API_KEY，或用 RUNPOD_KEY_FILE 指到存金鑰的文字檔。")
    return k


def api(method, path, body=None, base=REST):
    req = urllib.request.Request(base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key()}", "Content-Type": "application/json",
                                          "User-Agent": "shanshiba-workflow/1.0"})   # the default Python-urllib agent gets HTTP 403
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw.strip() else None
        except Exception:
            return e.code, raw.decode(errors="replace")[:300]


def gql(query):
    code, d = api("POST", "", {"query": query}, base=GQL)
    if code != 200:
        sys.exit(f"GraphQL {code}：金鑰的 GraphQL 權限至少要 Read。{d}")
    return d["data"]


def state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else None


def ssh_args(st, *extra):
    return ["-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + os.devnull,
            "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30", *extra]


def ssh(st, cmd, timeout=600, inp=None, check=True):
    r = subprocess.run(["ssh", *ssh_args(st, "-p", str(st["port"])), f"root@{st['ip']}", cmd], input=inp,
                       capture_output=True, timeout=timeout)
    out = (r.stdout + r.stderr).decode("utf-8", errors="replace")
    if check and r.returncode:
        sys.exit(f"ssh 指令失敗（{r.returncode}）：{cmd[:120]}\n{out[-800:]}")
    return out


def push_file(st, local, remote_dir):
    """Upload one file by piping it into `cat` (no scp/tar flags that differ between Windows and Linux)."""
    ssh(st, f"mkdir -p {remote_dir} && cat > {remote_dir}/{Path(local).name}", inp=Path(local).read_bytes(), timeout=1800)


def pull_file(st, remote, local):
    r = subprocess.run(["ssh", *ssh_args(st, "-p", str(st["port"])), f"root@{st['ip']}", f"cat {remote}"], capture_output=True, timeout=3600)
    if r.returncode:
        sys.exit(f"下載失敗：{remote}\n{r.stderr.decode(errors='replace')[-400:]}")
    Path(local).write_bytes(r.stdout)


def ensure_ssh_key():
    if not SSH_KEY.exists():
        SSH_KEY.parent.mkdir(exist_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "shanshiba-runpod", "-f", str(SSH_KEY)], check=True)
    return (SSH_KEY.with_suffix(".pub")).read_text().strip()


def stock(gpu_ids):
    out = []
    for g in gpu_ids:
        for secure in (True, False):
            d = gql('query { gpuTypes(input:{id:"%s"}) { displayName lowestPrice(input:{gpuCount:1, secureCloud:%s}) '
                    '{ stockStatus uninterruptablePrice } } }' % (g, "true" if secure else "false"))
            lp = d["gpuTypes"][0]["lowestPrice"] if d["gpuTypes"] else None
            if lp and lp.get("stockStatus"):
                out.append((g, "SECURE" if secure else "COMMUNITY", lp["stockStatus"], lp["uninterruptablePrice"]))
    return out


def cmd_check(a):
    me = gql("query { myself { clientBalance currentSpendPerHr } }")["myself"]
    print(f"[runpod] 餘額 US${me['clientBalance']:.2f}，目前花費 US${me['currentSpendPerHr']}/小時")
    for name, (ids, _) in GPUS.items():
        s = stock(ids)
        print(f"  {name}: " + ("; ".join(f"{g.split('Blackwell ')[-1]} {c} 庫存 {st} US${p}/hr" for g, c, st, p in s) if s else "目前沒有庫存"))
    code, _ = api("GET", "/pods")
    print("  REST Pods 權限：" + ("OK" if code == 200 else f"不行（HTTP {code}）→ 金鑰的 REST Pods 要 Read/Write"))


def cmd_start(a):
    st = state()
    if st:
        code, p = api("GET", f"/pods/{st['id']}")
        if code == 200 and p and p.get("desiredStatus") == "RUNNING":
            if "SETUP_DONE" in ssh(st, "cat /content/setup_h3.log 2>/dev/null", check=False):
                print(f"[runpod] 沿用已開好的 {st['gpu']}（{st['id']}）", flush=True)
                return st
        else:
            STATE.unlink()
    ids, inst = GPUS[a.gpu]
    pub = ensure_ssh_key()
    s = stock(ids)
    if not s:
        sys.exit(f"[runpod] {a.gpu} 現在沒有庫存，晚點再試或換 --gpu。")
    t0 = time.time(); p = None
    for cloud in ("SECURE", "COMMUNITY"):
        if not any(c == cloud for _, c, _, _ in s):
            continue
        body = {"name": f"h3-{a.gpu}-{time.strftime('%m%d%H%M')}", "imageName": IMAGE, "gpuTypeIds": ids, "gpuCount": 1,
                "cloudType": cloud, "containerDiskInGb": a.disk, "volumeInGb": 0, "ports": ["22/tcp"],
                "env": {"PUBLIC_KEY": pub}, "supportPublicIp": True}
        code, p = api("POST", "/pods", body)
        if code in (200, 201):
            print(f"[runpod] 已租 {a.gpu}（{cloud}，US${p.get('costPerHr')}/小時，pod {p['id']}）", flush=True)
            break
        print(f"[runpod] {cloud} 開不到（HTTP {code}）：{str(p)[:200]}", flush=True)
        p = None
    if not p:
        sys.exit("[runpod] 開機失敗。403＝金鑰的 REST Pods 沒有寫入權限；其他＝剛好被租走，稍後再試。")
    st = {"id": p["id"], "gpu": a.gpu, "instances": inst, "cost": p.get("costPerHr")}
    for _ in range(60):
        code, q = api("GET", f"/pods/{p['id']}")
        if q and q.get("publicIp") and (q.get("portMappings") or {}).get("22"):
            st.update(ip=q["publicIp"], port=q["portMappings"]["22"]); break
        time.sleep(10)
    else:
        sys.exit(f"[runpod] 等不到 SSH 位址；pod {p['id']} 還開著，記得 stop。")
    STATE.write_text(json.dumps(st), encoding="utf-8")
    for _ in range(40):
        if "ok" in ssh(st, "echo ok", timeout=40, check=False):
            break
        time.sleep(10)
    loc = ssh(st, "curl -s ipinfo.io", check=False)
    cc = (re.search(r'"country":\s*"(\w+)"', loc) or [None, "?"])[1]
    city = (re.search(r'"city":\s*"([^"]+)"', loc) or [None, "?"])[1]
    print(f"[runpod] 機房：{city}（{cc}）", flush=True)
    if cc in EXCLUDED:
        print("  ⚠ 這個機房在 MiniMax H3 授權排除的地區（美國／歐盟／英國／南韓），風險由你自負（不是法律意見）。", flush=True)
    tgz = repo_bundle()
    push_file(st, tgz, "/workspace")
    print("[runpod] 安裝 ffmpeg、torch 2.14 cu130 …", flush=True)
    prep = ssh(st, "mkdir -p /workspace/content /workspace/repo && ln -sfn /workspace/content /content && ln -sfn /workspace/repo /content/repo "
                   "&& tar xzf /workspace/repo.tgz -C /workspace/repo && bash /content/repo/cloud/vm/runpod_prep.sh 2>&1 | tail -6", timeout=1800)
    print("   " + "\n   ".join(l for l in prep.splitlines() if l.startswith("[prep]")), flush=True)
    if "PREP_DONE" not in prep:
        sys.exit("[runpod] 準備步驟失敗（pod 還開著，看完記得 stop）：\n" + prep[-800:])
    print(f"[runpod] 安裝 ComfyUI＋H3（{inst} 個 ComfyUI）…", flush=True)
    ssh(st, ENV + f"cd /content && (nohup python /content/repo/cloud/vm/setup_h3.py --instances {inst} > /content/setup_h3.log 2>&1 &)")
    while True:
        time.sleep(20)
        log = ssh(st, "cat /content/setup_h3.log", check=False)
        if "SETUP_DONE" in log:
            break
        if "FAILED" in log or "Traceback" in log:
            sys.exit("[runpod] 安裝失敗（pod 還開著，看完記得 stop）：\n" + log[-1200:])
    chk = ssh(st, "python -c 'import torch;print(\"TORCH\", torch.__version__)'; echo SLOW $(cat /content/comfy_*.log | grep -c 'need pytorch with cu130')",
              check=False)
    print(f"[runpod] torch {(re.search(r'TORCH (\S+)', chk) or [None, '?'])[1]}", flush=True)
    if not re.search(r"SLOW 0\b", chk) or not re.search(r"TORCH 2\.14", chk):
        print("  ⚠ comfy-kitchen 的 CUDA 加速沒開（torch 不是 2.14 cu130）→ H3 會慢 1.7–2 倍。", flush=True)
    pcie = ssh(st, "nvidia-smi --query-gpu=pcie.link.gen.max,pcie.link.width.max --format=csv,noheader", check=False).strip()
    m = re.search(r"(\d+),\s*(\d+)", pcie)
    if m:
        print(f"[runpod] PCIe 第 {m.group(1)} 代 x{m.group(2)}", flush=True)
        if a.gpu == "5090" and int(m.group(1)) < 4:
            # 2026-11-13: a 5090 host in Oslo had PCIe gen 1 -> H3 int8 does not fit in 32 GB and streams weights every step:
            # 5 s DMAD shot 123-140 s instead of 70 s on a normal host. PRO 6000 (96 GB) keeps all weights on the card.
            print("  ⚠ 這台的 PCIe 太慢：5090 跑 H3 要邊算邊從主記憶體搬權重，會慢將近一倍。建議 stop 後重開，或改 --gpu pro6000。", flush=True)
    print(f"[runpod] 可以開始跑 H3 了（{time.time() - t0:.0f} 秒）。用完記得 stop。", flush=True)
    return st


def cmd_batch(a):
    st = cmd_start(a)
    specs = [Path(s).resolve() for s in a.specs]
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
            shutil.copy2(src, jd / f"f{k}_{src.name}"); set_in(spec, path, f"f{k}_{src.name}")
        (jd / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        jobs.append({"id": jid}); where[jid] = out_dir(sp)
    (tmp / batch / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    zp = tmp / f"{batch}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (tmp / batch).rglob("*"):
            z.write(f, f.relative_to(tmp).as_posix())
    print(f"[batch] {len(jobs)} 鏡，上傳 {zp.stat().st_size / 1e6:.1f} MB …", flush=True)
    push_file(st, zp, "/content/jobs")
    ssh(st, ENV + f"cd /content/jobs && python -c \"import zipfile; zipfile.ZipFile('{batch}.zip').extractall('.')\" && "
                  f"(nohup python /content/repo/cloud/vm/run_batch.py {batch} > /content/jobs/{batch}.log 2>&1 &)")
    t0 = time.time(); seen = 0
    while True:
        time.sleep(15)
        txt = ssh(st, f"cat /content/jobs/{batch}/progress.jsonl 2>/dev/null; echo LOGTAIL; tail -c 800 /content/jobs/{batch}.log 2>/dev/null",
                  check=False)
        ev = [json.loads(l) for l in txt.split("LOGTAIL")[0].splitlines() if l.startswith("{")]
        for e in ev[seen:]:
            if e["event"] == "job":
                print(f"   {e['id']}: {'OK' if e['ok'] else 'FAIL'} {e['sec']} 秒" + ("" if e["ok"] else f"\n      {e['err'][-300:]}"), flush=True)
        seen = len(ev)
        if any(e["event"] == "DONE" for e in ev):
            break
        if "Traceback" in txt.split("LOGTAIL")[-1]:
            sys.exit("pod 上的批次程式出錯（pod 還開著）：\n" + txt.split("LOGTAIL")[-1])
    lz = tmp / f"{batch}_out.zip"
    pull_file(st, f"/content/jobs/{batch}_out.zip", lz)
    with zipfile.ZipFile(lz) as z:
        for m in z.namelist():
            jid, rel = m.split("/", 1)
            dst = where[jid] / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(z.read(m))
    okn = sum(e["ok"] for e in ev if e["event"] == "job")
    print(f"[batch] 完成 {okn}/{len(jobs)} 鏡，{time.time() - t0:.0f} 秒；成品已存回各 spec 旁邊。", flush=True)
    if a.stop_after:
        cmd_stop(a)
    if okn < len(jobs):
        sys.exit(1)


def cmd_status(a):
    st = state()
    if not st:
        print("[runpod] 沒有這個工具開的 pod。"); return
    code, p = api("GET", f"/pods/{st['id']}")
    print(f"[runpod] {st['gpu']} pod {st['id']}：{(p or {}).get('desiredStatus', code)}，US${st.get('cost')}/小時")


def cmd_stop(a):
    st = state()
    if not st:
        print("[runpod] 沒有這個工具開的 pod。"); return
    code, _ = api("DELETE", f"/pods/{st['id']}")
    if code in (200, 204, 404):
        STATE.unlink(missing_ok=True)
        print(f"[runpod] 已刪除 pod {st['id']}（停止計費；pod 上的模型與檔案一併刪除）。")
    else:
        sys.exit(f"[runpod] 刪除失敗（HTTP {code}）→ 到 console.runpod.io 的 Pods 手動 Terminate，避免繼續計費。")


def main():
    ap = argparse.ArgumentParser(description="MiniMax H3 on RunPod")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check"); sub.add_parser("status"); sub.add_parser("stop")
    for c in ("start", "batch"):
        p = sub.add_parser(c)
        p.add_argument("--gpu", choices=list(GPUS), default="5090")
        p.add_argument("--disk", type=int, default=120, help="container disk GB (models 55 GB + torch/ComfyUI)")
        if c == "batch":
            p.add_argument("specs", nargs="+")
            p.add_argument("--stop-after", action="store_true")
    a = ap.parse_args()
    {"check": cmd_check, "start": cmd_start, "batch": cmd_batch, "status": cmd_status, "stop": cmd_stop}[a.cmd](a)


if __name__ == "__main__":
    main()
