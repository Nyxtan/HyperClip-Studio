"""
Fast, non-blocking font installer for AI Clipper Suite.
Copies all bundled fonts directly to the user's fonts directory across Windows, macOS, and Linux.
No admin rights required.
"""
import os
import sys
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(HERE)
FONTS_DIR = os.path.join(ROOT_DIR, "assets", "fonts")

def install_fonts():
    if not os.path.isdir(FONTS_DIR):
        print(f"[Error] Fonts directory missing at: {FONTS_DIR}")
        return False

    font_files = [f for f in os.listdir(FONTS_DIR) if f.lower().endswith(".ttf")]
    if not font_files:
        print("[Warning] No .ttf font files found in assets/fonts.")
        return False

    if sys.platform == "win32":
        # Windows per-user font directory (no UAC / elevation needed)
        target = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")
    elif sys.platform == "darwin":
        target = os.path.expanduser("~/Library/Fonts")
    else:
        target = os.path.expanduser("~/.local/share/fonts")

    os.makedirs(target, exist_ok=True)
    count = 0
    for f in font_files:
        src = os.path.join(FONTS_DIR, f)
        dst = os.path.join(target, f)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
            count += 1

    print(f"[Success] Installed {count} new fonts into: {target}")
    return True

if __name__ == "__main__":
    install_fonts()
