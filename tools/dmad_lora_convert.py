"""Convert a DMAD MiniMax-H3 LoRA (Diffusers MiniMaxH3Transformer3DModel keys) to ComfyUI's H3 layout (2026-10-05).

DMAD (arXiv 2610.02188, huggingface.co/ZhengmingYu/DMAD) ships rank-128 LoRAs on
  transformer_blocks.N.attn.to_q/to_k/to_v/to_out.0, ff.net.0.proj, ff.net.2   (50 blocks)
  token_refiner.refiner_blocks.N.<same>                                          (2 blocks)
ComfyUI's H3 model fuses q/k/v into one `attn.qkv_proj` (order q, k, v along the output axis) and names the rest
`attn.out_proj`, `mlp.fc1`, `mlp.fc2`.  q/k/v fuse EXACTLY: A_qkv = cat(A_q, A_k, A_v) [3r, in],
B_qkv = block-diag(B_q, B_k, B_v) [3*out, 3r], alpha = 3r (scale stays alpha/rank = 1).  adaln is untouched by DMAD.
Output keys: diffusion_model.<module>.lora_down.weight / .lora_up.weight / .alpha  (ComfyUI LoRA loader format).

Usage: python dmad_lora_convert.py <in.safetensors> <out.safetensors>   (run with the H3 venv python)
"""
import re
import sys

import torch
from safetensors.torch import load_file, save_file

RENAME = {"attn.to_out.0": "attn.out_proj", "ff.net.0.proj": "mlp.fc1", "ff.net.2": "mlp.fc2"}
QKV = ("attn.to_q", "attn.to_k", "attn.to_v")


def split_key(k):
    """'<module>.<lora.down|lora.up|lora_A|lora_B>.weight' -> (module, 'A'|'B')"""
    for suf, ab in ((".lora.down.weight", "A"), (".lora.up.weight", "B"), (".lora_A.weight", "A"), (".lora_B.weight", "B")):
        if k.endswith(suf):
            return k[: -len(suf)], ab
    raise ValueError(f"unexpected key {k}")


def comfy_block(module):
    m = re.match(r"^transformer_blocks\.(\d+)\.(.+)$", module)
    if m:
        return f"blocks.{m.group(1)}", m.group(2)
    m = re.match(r"^token_refiner\.refiner_blocks\.(\d+)\.(.+)$", module)
    if m:
        return f"token_refiner.blocks.{m.group(1)}", m.group(2)
    raise ValueError(f"unexpected module {module}")


def convert(src):
    pairs = {}
    for k, t in src.items():
        mod, ab = split_key(k)
        pairs.setdefault(mod, {})[ab] = t
    out, qkv = {}, {}
    for mod, p in pairs.items():
        blk, sub = comfy_block(mod)
        if sub in QKV:
            qkv.setdefault(blk, {})[QKV.index(sub)] = p
            continue
        tgt = f"diffusion_model.{blk}.{RENAME[sub]}"
        r = p["A"].shape[0]
        out[tgt + ".lora_down.weight"] = p["A"].contiguous()
        out[tgt + ".lora_up.weight"] = p["B"].contiguous()
        out[tgt + ".alpha"] = torch.tensor(float(r))
    for blk, parts in qkv.items():
        assert sorted(parts) == [0, 1, 2], f"{blk}: missing q/k/v part"
        A = [parts[i]["A"] for i in range(3)]
        B = [parts[i]["B"] for i in range(3)]
        r = A[0].shape[0]
        a = torch.cat(A, 0)
        b = torch.zeros(sum(x.shape[0] for x in B), 3 * r, dtype=B[0].dtype)
        row = 0
        for i, x in enumerate(B):
            b[row: row + x.shape[0], i * r: (i + 1) * r] = x
            row += x.shape[0]
        tgt = f"diffusion_model.{blk}.attn.qkv_proj"
        out[tgt + ".lora_down.weight"] = a.contiguous()
        out[tgt + ".lora_up.weight"] = b.contiguous()
        out[tgt + ".alpha"] = torch.tensor(float(3 * r))
    return out, pairs


def check(out, pairs):
    """exactness: fused qkv delta == stacked per-part deltas for block 0 and refiner 0"""
    for blk_src, blk in (("transformer_blocks.0", "blocks.0"), ("token_refiner.refiner_blocks.0", "token_refiner.blocks.0")):
        ref = torch.cat([(pairs[f"{blk_src}.{q}"]["B"].float() @ pairs[f"{blk_src}.{q}"]["A"].float()) for q in QKV], 0)
        t = f"diffusion_model.{blk}.attn.qkv_proj"
        fused = out[t + ".lora_up.weight"].float() @ out[t + ".lora_down.weight"].float()
        err = (fused - ref).abs().max().item()
        print(f"[check] {blk} qkv max abs err {err:.2e}, shape {tuple(fused.shape)}")
        assert err < 1e-3


if __name__ == "__main__":
    src = load_file(sys.argv[1])
    out, pairs = convert(src)
    check(out, pairs)
    save_file(out, sys.argv[2], metadata={"source": sys.argv[1].split("\\")[-1].split("/")[-1],
                                          "converted_by": "C:/AI/tools/dmad_lora_convert.py (Diffusers -> ComfyUI H3, exact qkv fusion)"})
    n_mod = sum(1 for k in out if k.endswith(".alpha"))
    print(f"[ok] {len(src)} tensors / {len(pairs)} modules in -> {n_mod} ComfyUI modules out -> {sys.argv[2]}")
