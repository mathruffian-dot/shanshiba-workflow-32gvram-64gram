"""Runs ON the Colab VM (started by cloud/colab_h3.py start): ComfyUI 0.37.0 + MiniMax H3 + DMAD, then N ComfyUI instances.
Measured on a Colab G4 (RTX PRO 6000 Blackwell, 2026-10-10): about 3.5 minutes from a fresh VM to ready;
best throughput = 2 instances, --reserve-vram 46 each, models kept loaded (no --cache-none), second instance's jobs start 30 s later.
Uses the VM's own torch (2.11) - same H3 result as the Windows/torch 2.14 install (PSNR 45.9 dB vs Desk 5090).
Args: --instances 1|2|3 (default 2)   --encoder heretic|nvfp4 (default heretic = the int8 encoder the project uses)"""
import argparse, json, os, shutil, subprocess, threading, time, urllib.request
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--instances", type=int, default=2)
ap.add_argument("--encoder", default="heretic", choices=["heretic", "nvfp4"])
a = ap.parse_args()

AI = Path(os.environ.get("AI_ROOT", "/content/AI")); REPO = Path(os.environ.get("REPO", "/content/repo"))
C = AI / "H3" / "ComfyUI-0.36.0"          # same folder name as the Windows install, so the download manifests map 1:1
T0 = time.time()
STATE = Path("/content/h3_state.json")


def mark(k, v=None):
    v = v if v is not None else round(time.time() - T0, 1)
    print(f"[setup] {k} = {json.dumps(v, ensure_ascii=False)}", flush=True)


def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-2000:], flush=True)
        raise SystemExit(f"FAILED: {cmd}")
    return r.stdout.strip()


try:
    ip = json.loads(urllib.request.urlopen("https://ipinfo.io/json", timeout=15).read())
    mark("region", {k: ip.get(k) for k in ("city", "region", "country")})
except Exception as e:
    mark("region", f"unknown ({e})")
mark("gpu", sh("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"))

# 1. models (background): H3 core + text encoder + DMAD lora_critic, via the repo's download.py (16 streams per file, SHA-256)
man = []
for f in ["downloads.json", "downloads_uncensored.json" if a.encoder == "heretic" else None, "downloads_dmad.json"]:
    if f:
        man += json.loads((REPO / "setup" / f).read_text(encoding="utf-8-sig"))
man = [x for x in man if not ("nvfp4" in x["destination"] and a.encoder == "heretic") and "full_critic" not in x["destination"]]
Path("/content/h3_models.json").write_text(json.dumps(man, indent=1))
dl = subprocess.Popen(f"AI_ROOT={AI} python {REPO}/setup/download.py /content/h3_models.json > /content/h3_download.log 2>&1", shell=True)
mark("downloads_started", f"{len(man)} files, {round(sum(x['size'] for x in man) / 1e9, 1)} GB")

# 2. ComfyUI 0.37.0 + packages with uv on the VM's python (keeps Colab's torch)
if not (C / "main.py").exists():
    sh(f"git clone -q --depth 1 --branch v0.37.0 https://github.com/comfyanonymous/ComfyUI /content/ComfyUI_src"
       f" && mkdir -p {C} && cp -rn /content/ComfyUI_src/. {C}/")
    sh("pip install -q uv")
    sh(f"grep -viE '^(torch|torchvision|torchaudio)([=<> ]|$)' {C}/requirements.txt > /content/req_comfy.txt"
       f" && uv pip install --system -q -r /content/req_comfy.txt comfy-kitchen==0.2.35")
    sh(f"sed 's#C:/AI/H3/models#{AI}/H3/models#' {REPO}/setup/extra_model_paths.yaml > {C}/extra_model_paths.yaml")
mark("comfy_installed")
dl.wait()
tail = Path("/content/h3_download.log").read_text(errors="replace")[-400:]
if dl.returncode:
    raise SystemExit(f"FAILED: model download\n{tail}")
mark("models_ready")

lora = C / "models" / "loras" / "dmad_h3_4step_lora_critic_comfy.safetensors"
if not lora.exists():
    sh(f"python {REPO}/tools/dmad_lora_convert.py {C}/models/loras/dmad_raw/dmad_minimax_h3_4step_lora_critic.safetensors {lora}")
mark("dmad_converted")


# 3. N ComfyUI instances (own input/output/user folders, shared models)
def instance_dir(i):
    if i == 0:
        return C
    d = Path(f"/content/ComfyUI_{i}")
    if not d.exists():
        top = {"models", "input", "output", "user", "temp"}          # top level only - comfy/ldm/models is code
        shutil.copytree(C, d, ignore=lambda p, names: [n for n in names if Path(p) == C and n in top], symlinks=True)
        (d / "models").symlink_to(C / "models")
        shutil.copy(C / "extra_model_paths.yaml", d / "extra_model_paths.yaml")
    return d


subprocess.run("pkill -f 'main.py --listen'", shell=True); time.sleep(2)
reserve = {1: None, 2: 46, 3: 62}.get(a.instances, 62)
inst = []
for i in range(a.instances):
    d = instance_dir(i); port = 8188 + i
    extra = f"--reserve-vram {reserve}" if reserve else ""
    subprocess.Popen(f"nohup python main.py --listen 127.0.0.1 --port {port} --disable-auto-launch --preview-method none "
                     f"--fast fp16_accumulation {extra} > /content/comfy_{i}.log 2>&1 &", shell=True, cwd=d)
    inst.append({"dir": str(d), "port": port})
for x in inst:
    for _ in range(300):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{x['port']}/system_stats", timeout=2); break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit(f"FAILED: ComfyUI on port {x['port']} did not start (see /content/comfy_*.log)")
STATE.write_text(json.dumps({"instances": inst, "encoder": a.encoder, "ready_at": time.time()}))
mark("comfy_ready", f"{a.instances} instance(s)")
print("SETUP_DONE", flush=True)
