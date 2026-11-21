"""
auth_youtube.py — Standalone one-time authorization helper for YouTube
"""
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

CLIENT_SECRET_FILE = Path(__file__).parent / ".credentials" / "client_secret.json"
TOKEN_FILE = Path(__file__).parent / ".credentials" / "youtube_token.json"


def main():
    if not CLIENT_SECRET_FILE.exists():
        sys.exit(f"File not found: {CLIENT_SECRET_FILE}")
    print("\nOpening Google OAuth in your default browser...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    print(f"\nSUCCESS! OAuth token saved to: {TOKEN_FILE}")
    print("You can now upload clips directly to YouTube without any manual steps.\n")


if __name__ == "__main__":
    main()
