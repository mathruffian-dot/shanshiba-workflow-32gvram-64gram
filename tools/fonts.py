"""Font paths that work on Windows and on Linux/Colab (2026-10-10).
Windows: the system 標楷體 / 微軟正黑體 used by the original project.
Linux:   apt install fonts-noto-cjk fonts-arphic-ukai   (cloud/vm/install_full.sh does this)
Override any of them with env FONT_KAI / FONT_JH / FONT_JHBD / SUB_FONT_NAME."""
import os

_C = {
    "kai": ["C:/Windows/Fonts/kaiu.ttf", "/usr/share/fonts/truetype/arphic/ukai.ttc",
            "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"],
    "jh": ["C:/Windows/Fonts/msjh.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"],
    "jhbd": ["C:/Windows/Fonts/msjhbd.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"],
}


def font(kind):
    """Path of the first font of this kind that exists ('kai' title, 'jh' regular, 'jhbd' bold)."""
    env = os.environ.get("FONT_" + kind.upper())
    if env:
        return env
    for p in _C[kind]:
        if os.path.exists(p):
            return p
    return _C[kind][0]


# family name for libass subtitles (ffmpeg subtitles= filter / ASS Style lines)
SUB_FONT_NAME = os.environ.get("SUB_FONT_NAME", "Microsoft JhengHei" if os.name == "nt" else "Noto Sans CJK TC")
