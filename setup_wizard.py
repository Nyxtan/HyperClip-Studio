"""
setup_wizard.py — Interactive Onboarding & Publishing Configuration Wizard
Handles step-by-step onboarding for:
1. Google Gemini API Key (AI titles, descriptions, hashtags, viral hooks)
2. Publishing Engine:
   - Direct Zero-Middleman YouTube Shorts via Google OAuth 2.0
   - Multi-Platform Social Publishing via Zernio (Instagram Reels, YouTube, TikTok)
   - Browser Automation Helper (Agent/Browser launch for 1-click login)
"""

import os
import sys
import json
import webbrowser
from pathlib import Path

HERE = Path(__file__).parent.resolve()
CREDENTIALS_DIR = HERE / ".credentials"
CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
ENV_FILE = HERE / ".env"


def set_user_env(key, val):
    os.environ[key] = val
    if sys.platform == "win32":
        try:
            import subprocess
            subprocess.run(["setx", key, val], capture_output=True, text=True)
        except Exception:
            pass
    # Also save to .env
    lines = []
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if not l.startswith(f"{key}=")]
    lines.append(f"{key}={val}\n")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def run_wizard():
    print("\n" + "="*65)
    print(" 🚀  GTA AUTO-CLIPPER & PUBLISHING SETUP WIZARD")
    print("="*65 + "\n")

    # -------------------------------------------------------------
    # Step 1: Google Gemini API Key
    # -------------------------------------------------------------
    current_gemini = os.environ.get("GEMINI_API_KEY", "").strip()
    print("STEP 1: Google Gemini API Key (AI Viral Titles, Hooks & Tags)")
    print("  Used for generating curiosity hooks, high-CTR titles, and platform tags.")
    if current_gemini:
        print(f"  [Found existing key: {current_gemini[:6]}...{current_gemini[-4:]}]")
        change = input("  Keep current key? [Y/n]: ").strip().lower()
        if change == "n":
            new_key = input("  Paste new Gemini API Key: ").strip()
            if new_key:
                set_user_env("GEMINI_API_KEY", new_key)
                print("  [✓] Updated GEMINI_API_KEY.")
    else:
        new_key = input("  Paste your Google Gemini API Key (or press Enter to open AI Studio): ").strip()
        if not new_key:
            print("  Opening https://aistudio.google.com/app/apikey in your browser...")
            webbrowser.open("https://aistudio.google.com/app/apikey")
            new_key = input("  Paste your Gemini API Key once copied: ").strip()
        if new_key:
            set_user_env("GEMINI_API_KEY", new_key)
            print("  [✓] Saved GEMINI_API_KEY.")
        else:
            print("  [!] Skipped. Engine will use high-converting fallback viral templates.")

    # -------------------------------------------------------------
    # Step 2: Choose Publishing Destination
    # -------------------------------------------------------------
    print("\n" + "-"*65)
    print("STEP 2: Choose Automated Reel & Short Publishing Method")
    print("  1. Direct YouTube Shorts (Google OAuth 2.0 — Local, Free, Zero-Middleman)")
    print("  2. Multi-Platform via Zernio (Instagram Reels + YouTube Shorts + TikTok)")
    print("  3. Both (Direct YouTube Shorts + Zernio Instagram Reels)")
    print("  4. Skip Publishing (Clip & edit only, save locally to output/)")
    print("-"*65)

    choice = input("Select an option [1-4] (default: 1): ").strip() or "1"

    # Option 1: Direct YouTube OAuth
    if choice in ["1", "3"]:
        print("\n[Direct YouTube Shorts Setup]")
        client_secret = CREDENTIALS_DIR / "client_secret.json"
        token_file = CREDENTIALS_DIR / "youtube_token.json"
        if token_file.exists():
            print("  [✓] YouTube OAuth token already active (youtube_token.json found).")
        elif client_secret.exists():
            print("  Opening browser for Google Account 1-click authorization...")
            try:
                import auth_youtube
                auth_youtube.main()
            except Exception as e:
                print(f"  [!] OAuth flow error: {e}")
        else:
            print(f"  [!] Missing client_secret.json in {CREDENTIALS_DIR}.")
            print("  Please download your OAuth client credentials from Google Cloud Console.")

    # Option 2: Zernio
    if choice in ["2", "3"]:
        print("\n[Zernio Multi-Platform Setup]")
        print("  Zernio coordinates simultaneous publishing to Instagram Reels and YouTube.")
        current_zernio = os.environ.get("ZERNIO_API_KEY", "").strip()
        if current_zernio:
            print(f"  [Found existing Zernio key: {current_zernio[:8]}...]")
            keep = input("  Keep current Zernio key? [Y/n]: ").strip().lower()
            if keep == "n":
                current_zernio = ""

        if not current_zernio:
            z_key = input("  Paste your Zernio API Key (or press Enter to open Zernio login): ").strip()
            if not z_key:
                print("  Opening https://zernio.com/dashboard in your browser...")
                webbrowser.open("https://zernio.com/dashboard/api-keys")
                z_key = input("  Paste your Zernio API Key once copied: ").strip()
            if z_key:
                set_user_env("ZERNIO_API_KEY", z_key)
                print("  [✓] Saved ZERNIO_API_KEY.")

        # Account IDs
        cur_ig = os.environ.get("ZERNIO_INSTAGRAM_ACCOUNT_ID", "").strip()
        cur_yt = os.environ.get("ZERNIO_YOUTUBE_ACCOUNT_ID", "").strip()
        if cur_ig and cur_yt:
            print(f"  [✓] Connected Instagram ID: {cur_ig}")
            print(f"  [✓] Connected YouTube ID: {cur_yt}")
        else:
            print("  Visit https://zernio.com/dashboard/accounts to link your Instagram and YouTube accounts.")
            ig_id = input("  Enter Zernio Instagram Account ID (or press Enter to skip): ").strip()
            if ig_id:
                set_user_env("ZERNIO_INSTAGRAM_ACCOUNT_ID", ig_id)
            yt_id = input("  Enter Zernio YouTube Account ID (or press Enter to skip): ").strip()
            if yt_id:
                set_user_env("ZERNIO_YOUTUBE_ACCOUNT_ID", yt_id)

    print("\n" + "="*65)
    print(" ✅  CONFIGURATION COMPLETE!")
    print("="*65)
    print("\nYou can now start the continuous auto-clipper loop in PowerShell with:")
    print("  .\\autopilot.ps1 -Url \"https://www.youtube.com/live/...\" -AutoPost\n")


if __name__ == "__main__":
    run_wizard()
