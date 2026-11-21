"""
direct_youtube_uploader.py — Direct Zero-Middleman YouTube Shorts Uploader
Uses Google OAuth 2.0 and YouTube Data API v3 directly from your machine.
"""
import os
import sys
import json
import argparse
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

CLIENT_SECRET_FILE = Path(__file__).parent / ".credentials" / "client_secret.json"
TOKEN_FILE = Path(__file__).parent / ".credentials" / "youtube_token.json"


def get_authenticated_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired YouTube OAuth token...")
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_FILE.exists():
                sys.exit(f"Client secret file not found: {CLIENT_SECRET_FILE}")
            print("Launching one-time Google OAuth browser authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
            print(f"Saved token to {TOKEN_FILE}")
    return build("youtube", "v3", credentials=creds)


def upload_short(video_path, metadata_path, privacy_status="public"):
    with open(metadata_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    title = meta.get("title") or "Viral Moment #Shorts"
    if "#Shorts" not in title and "#shorts" not in title:
        title = f"{title[:85]} #Shorts"

    description = meta.get("youtube_description") or f"{title}\n\nCredit: {meta.get('streamer', 'IShowSpeed')}\n#Shorts"
    tags = meta.get("hashtags") or ["Shorts", "GTA6", "IShowSpeed", "Gaming"]

    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": "20",  # Gaming
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    print(f"Uploading {video_path} to YouTube Shorts...")
    print(f"Title: {title}")
    print(f"Privacy: {privacy_status}")

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=1024*1024*5)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    video_url = f"https://youtube.com/shorts/{video_id}"
    print(f"\nSUCCESS! Video uploaded directly to YouTube: {video_url}")

    meta["youtube_url"] = video_url
    meta["youtube_id"] = video_id
    meta["uploaded_at"] = response.get("snippet", {}).get("publishedAt")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return video_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload vertical video directly to YouTube Shorts")
    parser.add_argument("clip", help="Clip base name or path to .json/.mp4")
    parser.add_argument("--privacy", choices=["public", "unlisted", "private"], default="public")
    args = parser.parse_args()

    base = Path(args.clip).with_suffix("")
    mp4_file = base.with_suffix(".mp4")
    json_file = base.with_suffix(".json")

    if not mp4_file.exists() or not json_file.exists():
        sys.exit(f"Clip files not found: {mp4_file} or {json_file}")

    upload_short(mp4_file, json_file, privacy_status=args.privacy)
