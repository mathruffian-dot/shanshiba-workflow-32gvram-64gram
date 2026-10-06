"""〈D-7〉台詞與聲音來源。LINES: (id, speaker, 字幕文字)。TTS 文字去掉刪節號與～。
speaker：shb 山獅霸（三師爸克隆）／xw 小雯（只用 Breeze 直出）／afu 阿福／ahe 阿禾旁白。"""
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CH = ROOT / "角色資產/老師這次換你"
REFS = {
    "shb": (ROOT / "角色資產/老師_山獅霸/voice_ref.wav"   # 原專案為本人授權錄音，不公開,
            "<參考錄音的逐字稿>"),
    "xw": (CH / "班長小雯/voice_ref.wav", "各位同學請安靜，我是班長，老師馬上就要到了。"),
    "afu": (CH / "阿福/voice_ref.wav", "老師,我剛剛真的都有聽,我只是眼睛閉起來而已啦。"),
    "ahe": (ROOT / "短片/阿福三個絕招_20260929/voice_tw/ref/ahe_tw.wav", None),   # 逐字稿由 voice_stage1.py 用 ASR 取得
}
EDGE = {"shb": "zh-TW-YunJheNeural", "ahe": "zh-TW-YunJheNeural", "afu": "zh-TW-YunJheNeural", "xw": "zh-TW-HsiaoChenNeural"}
LINES = [
    ("L01", "shb", "下週段考喔。"), ("L02", "xw", "老師，是下週四嗎？"), ("L03", "shb", "……對。"),
    ("L05", "shb", "明天段考。早點睡。"), ("L14", "afu", "又有學習單～"), ("L16", "afu", "……今天，段考？"),
    ("L17", "afu", "老師，考卷……是熱的。"), ("L19", "shb", "……開始作答。"), ("L21", "afu", "……好溫暖。"),
    ("V01", "ahe", "段考，有三種人。"), ("V02", "ahe", "第一種，先知先覺。一週前就開始。"),
    ("V03", "ahe", "第二種跟第三種，那時候還沒出現。"), ("V04", "ahe", "第二種，後知後覺。也就是我。"),
    ("V05", "ahe", "沒關係。一個晚上，夠了。"), ("V06", "ahe", "跟班長借筆記好了。"), ("V07", "ahe", "……上週四。"),
    ("V08", "ahe", "第三種人，睡得很好。"), ("V09", "ahe", "第三種，不知不覺。"), ("V10", "ahe", "原來，段考有四種人。"),
]
TTS = {lid: tx.replace("……", "").replace("～", "！") for lid, _, tx in LINES}
TTS["L03"] = "對。"; TTS["V07"] = "上週四。"
