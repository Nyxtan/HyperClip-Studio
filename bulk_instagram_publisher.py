"""Bulk-publish all remaining unposted clips directly to Instagram Reels.
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

API = "https://zernio.com/api/v1"
from zernio_publish import upload_and_schedule

def main():
    api_key = os.environ.get("ZERNIO_API_KEY")
    ig_acc = os.environ.get("ZERNIO_INSTAGRAM_ACCOUNT_ID")
    if not api_key or not ig_acc:
        sys.exit("ZERNIO_API_KEY and ZERNIO_INSTAGRAM_ACCOUNT_ID must be set.")

    output_dir = Path("output")
    clips = sorted(output_dir.glob("gta-*.json"))
    unposted = []

    for c in clips:
        try:
            with c.open("r", encoding="utf-8") as f:
                meta = json.load(f)
            if not meta.get("zernio_post_id") and c.with_suffix(".mp4").is_file():
                unposted.append((c, meta))
        except Exception:
            continue

    print(f"Found {len(unposted)} unposted clips ready for Instagram.")
    accounts = [("instagram", ig_acc)]

    success = 0
    for idx, (json_path, meta) in enumerate(unposted, start=1):
        video_path = json_path.with_suffix(".mp4")
        if not meta.get("instagram_caption"):
            title = meta.get("title", f"IShowSpeed GTA 6 Moments #{idx}")
            meta["instagram_caption"] = f"{title}\n\nCredit: IShowSpeed\n#IShowSpeed #GTA6 #Gaming #Shorts #Reels"
        if not meta.get("title"):
            meta["title"] = f"IShowSpeed GTA 6 Highlight #{idx}"
        if not meta.get("youtube_description"):
            meta["youtube_description"] = meta["instagram_caption"]

        meta["approved"] = True
        print(f"\n[{idx}/{len(unposted)}] Publishing to Instagram: {meta['title']} ({video_path.name})...")

        try:
            result = upload_and_schedule(video_path, json_path, meta, accounts, "now", api_key)
            post_id = result.get("_id")
            print(f"  -> SUCCESS! Live on Instagram (Post ID: {post_id})")
            success += 1
            time.sleep(15)  # 15s delay between uploads to stay within API rate limits
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                print(f"  -> Rate limit hit (429). Sleeping 65 seconds to reset window...")
                time.sleep(65)
                # Retry once
                try:
                    result = upload_and_schedule(video_path, json_path, meta, accounts, "now", api_key)
                    post_id = result.get("_id")
                    print(f"  -> SUCCESS on retry! (Post ID: {post_id})")
                    success += 1
                    time.sleep(15)
                except Exception as retry_err:
                    print(f"  -> Retry failed: {retry_err}")
            else:
                print(f"  -> FAILED: {e}")
                time.sleep(10)
        except Exception as e:
            print(f"  -> FAILED: {e}")
            time.sleep(10)

    print(f"\nAll done! Successfully published {success}/{len(unposted)} clips to Instagram Reels.")

if __name__ == "__main__":
    main()
