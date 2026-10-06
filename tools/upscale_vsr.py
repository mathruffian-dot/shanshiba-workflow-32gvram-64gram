"""RTX VSR 1080p, original audio packet copy, and matched-frame comparisons."""
import json
import time
import argparse
from pathlib import Path
import av
import numpy as np
import torch
import nvvfx
from PIL import Image, ImageDraw

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--quality', default='ULTRA', help='nvvfx QualityLevel name, e.g. ULTRA or HIGHBITRATE_ULTRA')
args = parser.parse_args()
src = args.source
dest = args.output
if dest.exists():
    raise FileExistsError(dest)
folder = dest.parent
folder.mkdir(parents=True,exist_ok=True)
silent = folder/'vsr_video_only.mp4'
start = time.perf_counter()
torch.cuda.reset_peak_memory_stats()
checks = []
with av.open(str(src)) as inp, av.open(str(silent), 'w') as out:
    fps = inp.streams.video[0].average_rate
    stream = out.add_stream('libx264', rate=fps)
    stream.width, stream.height, stream.pix_fmt = 1920,1080,'yuv420p'
    stream.options = {'crf':'16','preset':'slow'}
    with nvvfx.VideoSuperRes(getattr(nvvfx.effects.QualityLevel, args.quality)) as sr:
        sr.output_width, sr.output_height = 1920,1080
        sr.load()
        for i,frame in enumerate(inp.decode(video=0)):
            rgb = frame.to_ndarray(format='rgb24')
            tensor = torch.from_numpy(rgb).cuda().permute(2,0,1).float().div_(255).contiguous()
            result = torch.from_dlpack(sr.run(tensor).image).permute(1,2,0).clamp(0,1)
            image = result.mul(255).round().byte().cpu().numpy()
            if not image.any():
                raise RuntimeError('VSR returned a black frame')
            if i in (12,62,110):
                before = Image.fromarray(rgb).resize((1920,1080),Image.Resampling.LANCZOS)
                after = Image.fromarray(image)
                after.save(folder/f'vsr_frame_{i:03}.png')
                # Both crops use the same target-space box, no extra resizing.
                box=(650,80,1270,760)
                compare=Image.new('RGB',(1240,720),'#202020')
                compare.paste(before.crop(box),(0,40))
                compare.paste(after.crop(box),(620,40))
                draw=ImageDraw.Draw(compare)
                draw.text((20,12),f'{rgb.shape[0]}p source - Lanczos enlarged',fill='white')
                draw.text((640,12),f'RTX VSR {args.quality} - 1080p',fill='white')
                compare.save(folder/f'comparison_{i:03}.png')
                baseline=np.asarray(before).astype(float)
                checks.append({'frame':i,'mean_absolute_difference_from_lanczos':float(np.abs(image.astype(float)-baseline).mean())})
            encoded=av.VideoFrame.from_ndarray(image,format='rgb24')
            encoded.pts=i
            for packet in stream.encode(encoded): out.mux(packet)
            if i % 24 == 0: print(f'FRAME {i}',flush=True)
        count=i+1
        for packet in stream.encode(): out.mux(packet)

# Re-mux encoded video and original AAC packets; no speech resynthesis.
with av.open(str(silent)) as vin, av.open(str(src)) as ain, av.open(str(dest),'w') as out:
    vs=out.add_stream_from_template(vin.streams.video[0])
    aus=out.add_stream_from_template(ain.streams.audio[0])
    packets=[]
    for source,instream,target in [(vin,vin.streams.video[0],vs),(ain,ain.streams.audio[0],aus)]:
        for p in source.demux(instream):
            if p.dts is not None:
                t=float(p.dts*p.time_base)
                p.stream=target
                packets.append((t,p))
    for _,p in sorted(packets,key=lambda item:item[0]): out.mux(p)
report={'engine':'NVIDIA RTX VSR','quality':args.quality,'source':str(src),'output':str(dest),'width':1920,'height':1080,'frames':count,'fps':24,'elapsed_seconds':time.perf_counter()-start,'torch_peak_allocated_GiB':torch.cuda.max_memory_allocated()/1024**3,'audio':'original AAC packets copied','checks':checks}
(folder/'vsr_result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
