"""Make the Google Colab CLI start on Windows (tested with google-colab-cli 0.7.4, 2026-10-10).
The CLI officially supports only Linux/macOS: colab_cli/console.py does `import termios` / `import tty` at the top, and every
command imports it, so even `colab version` crashes on Windows. Only the interactive `colab console` needs those modules.
This wraps the two imports in try/except (backup: console.py.bak). After it: new / exec / upload / download / usage / stop /
sessions work; `colab console` and `colab ssh` still do not (cloud/colab_h3.py never uses them). Re-run after updating the CLI.
  python cloud/colab_cli_windows_patch.py          (or: --undo)"""
import shutil, subprocess, sys
from pathlib import Path


def find():
    exe = shutil.which("colab")
    roots = []
    if exe:   # uv tool installs live in %APPDATA%\uv\tools\google-colab-cli
        roots.append(Path.home() / "AppData" / "Roaming" / "uv" / "tools" / "google-colab-cli")
    try:
        import colab_cli  # pip install into the current python
        return Path(colab_cli.__file__).parent / "console.py"
    except Exception:
        pass
    for r in roots:
        for p in r.rglob("colab_cli/console.py"):
            return p
    sys.exit("找不到 colab_cli/console.py：先執行  uv tool install google-colab-cli")


p = find(); bak = p.with_suffix(".py.bak")
if "--undo" in sys.argv:
    if bak.exists():
        shutil.copy2(bak, p); print("restored", p)
    sys.exit(0)
s = p.read_text(encoding="utf-8")
if "termios = None" in s:
    print("already patched:", p)
else:
    if not bak.exists():
        shutil.copy2(p, bak)
    s = s.replace("import termios\n", "try:  # Windows has no termios/tty; only `colab console` needs them\n    import termios\nexcept ImportError:\n    termios = None\n", 1)
    s = s.replace("import tty\n", "try:\n    import tty\nexcept ImportError:\n    tty = None\n", 1)
    p.write_text(s, encoding="utf-8")
    print("patched", p, "(backup", bak.name + ")")
r = subprocess.run([shutil.which("colab") or "colab", "version"], capture_output=True, text=True)
print((r.stdout + r.stderr).strip()[-300:])
