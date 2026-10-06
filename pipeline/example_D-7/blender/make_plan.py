"""〈D-7〉教室鏡頭的鏡位契約 camera_plan_v1.json（Blender 原始座標，成圖由 make_sheet.py 鏡射）。
座位沿用〈拿下頭套的人〉：阿禾 (0.6,-0.42) 第一排正中；小雯 (2.1,-0.42) 第一排靠走廊側；阿福 (-0.9,0.83) 阿禾斜後方（窗側）。前門在走廊側靠黑板。"""
import json
C = {
    "WIDE_BACK": ([3.9, 7.4, 2.5], [-0.3, -2.6, 1.1], 22),
    "XW_MS": ([1.6, -1.95, 1.45], [2.1, -0.42, 1.25], 32),
    "T_DOOR": ([1.5, -0.7, 1.5], [3.25, -2.3, 1.6], 35),
    "THREE": ([0.6, -2.6, 2.0], [0.6, 0.1, 1.0], 24),
    "T_DESK": ([0.6, -1.1, 1.55], [0.6, -2.62, 1.45], 35),
    "T_CU": ([0.6, -1.5, 1.6], [0.6, -2.62, 1.65], 50),
    "AHE_MS": ([1.3, -1.6, 1.4], [0.6, -0.42, 1.1], 32),
    "AFU_MS": ([-0.1, -0.45, 1.45], [-0.9, 0.83, 1.15], 32),
}
S = [("S01", "WIDE_BACK", dict(teacher="door"), "下課；山獅霸在前門說話"),
     ("S02", "XW_MS", dict(teacher="door"), "小雯抬頭問老師"),
     ("S03", "T_DOOR", dict(teacher="door"), "老師在前門停一拍"),
     ("S04", "THREE", dict(teacher="hidden"), "三人正面同框：左小雯、中阿禾、右阿福"),
     ("S05", "T_DESK", dict(teacher="desk"), "放學，老師在講桌後"),
     ("S06", "AHE_MS", dict(teacher="desk"), "阿禾拉書包拉鍊停住"),
     ("S12", "THREE", dict(teacher="hidden"), "D-0 早自習三人同框"),
     ("S13", "T_DESK", dict(teacher="desk"), "老師抱考卷＋咖啡"),
     ("S14", "AFU_MS", dict(teacher="desk"), "阿福接卷往後傳"),
     ("S16", "AFU_MS", dict(teacher="desk"), "阿福：今天段考？"),
     ("S17", "AFU_MS", dict(teacher="desk"), "阿福：考卷是熱的"),
     ("S19", "T_CU", dict(teacher="desk"), "老師又來了表情"),
     ("S21", "AFU_MS", dict(teacher="desk"), "阿福雙手貼考卷")]
setups = [dict(st, id="L_" + sid, camera=cam) for sid, cam, st, _ in S]
shots = [dict(shot=sid, camera=cam, action=a, layer="電影層", method="H3", sec=0, frames_sec=0, speaker="", line="") for sid, cam, _, a in S]
json.dump(dict(film="〈D-7〉", cameras={k: dict(loc=v[0], target=v[1], lens=v[2]) for k, v in C.items()}, setups=setups, shots=shots),
          open("camera_plan_v1.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(S))
