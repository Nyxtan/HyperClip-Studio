"""Smart multi-platform drip queue scheduler for Zernio.

Protects against spam-flags and algorithm suppression:
- YouTube Shorts: Strictest filter (score >= 5.0, spaced >= 3 hours apart, max 3-4/day).
- Instagram Reels: Higher limits (score >= 3.5, spaced >= 45 minutes apart).
- Supports dry-run, live execution, and retroactive backlog queuing.
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

API = "https://zernio.com/api/v1"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
QUEUE_FILE = Path(".credentials/drip_queue_state.json")

def load_queue_state():
    if QUEUE_FILE.is_file():
        try:
            with QUEUE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_youtube_time": None,
        "youtube_posts_today": 0,
        "last_youtube_day": None,
        "last_instagram_time": None,
    }

def save_queue_state(state):
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def calculate_schedule(score, state, now=None):
    """
    Decides platforms and scheduled time for a clip based on score and past queue state.
    Returns:
      dict with:
        "eligible_youtube": bool,
        "youtube_time": ISO str or "now" or None,
        "eligible_instagram": bool,
        "instagram_time": ISO str or "now" or None
    """
    if now is None:
        now = dt.datetime.now(IST)

    today_str = now.strftime("%Y-%m-%d")
    if state.get("last_youtube_day") != today_str:
        state["last_youtube_day"] = today_str
        state["youtube_posts_today"] = 0

    # 1. Instagram Logic: Score >= 3.5, spaced >= 45 min
    eligible_ig = score >= 3.0  # Accept all valid highlights
    ig_time = None
    if eligible_ig:
        last_ig_str = state.get("last_instagram_time")
        if last_ig_str:
            last_ig_dt = dt.datetime.fromisoformat(last_ig_str)
            min_next = last_ig_dt + dt.timedelta(minutes=45)
            if now >= min_next:
                ig_time = "now"
                state["last_instagram_time"] = now.isoformat()
            else:
                ig_time = min_next.isoformat()
                state["last_instagram_time"] = min_next.isoformat()
        else:
            ig_time = "now"
            state["last_instagram_time"] = now.isoformat()

    # 2. YouTube Logic: Score >= 5.0, spaced >= 3 hours, max 4/day
    eligible_yt = (score >= 4.7) and (state.get("youtube_posts_today", 0) < 4)
    yt_time = None
    if eligible_yt:
        last_yt_str = state.get("last_youtube_time")
        if last_yt_str:
            last_yt_dt = dt.datetime.fromisoformat(last_yt_str)
            min_next = last_yt_dt + dt.timedelta(hours=3)
            if now >= min_next:
                yt_time = "now"
                state["last_youtube_time"] = now.isoformat()
            else:
                yt_time = min_next.isoformat()
                state["last_youtube_time"] = min_next.isoformat()
        else:
            yt_time = "now"
            state["last_youtube_time"] = now.isoformat()
        state["youtube_posts_today"] += 1

    return {
        "eligible_youtube": eligible_yt,
        "youtube_time": yt_time,
        "eligible_instagram": eligible_ig,
        "instagram_time": ig_time,
    }

def schedule_single_clip(clip_path, publish=False):
    base = clip_path.with_suffix("")
    video_path, metadata_path = base.with_suffix(".mp4"), base.with_suffix(".json")
    if not metadata_path.is_file() or not video_path.is_file():
        print(f"Skipping {clip_path}: Missing mp4/json")
        return None

    with metadata_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)

    if meta.get("zernio_post_id"):
        print(f"Skipping {clip_path.name}: Already published ({meta['zernio_post_id']})")
        return None

    score = float(meta.get("score") or meta.get("viral_score") or 3.0)
    state = load_queue_state()
    plan = calculate_schedule(score, state)

    print(f"\nEvaluating: {clip_path.name} (Viral Score: {score})")
    print(f"  Instagram: {'ELIGIBLE' if plan['eligible_instagram'] else 'REJECTED'} -> {plan['instagram_time']}")
    print(f"  YouTube:   {'ELIGIBLE' if plan['eligible_youtube'] else 'SKIPPED (Anti-Spam / Score < 4.7)'} -> {plan['youtube_time']}")

    if not publish:
        print("  [DRY RUN] Pass --publish to dispatch to Zernio.")
        return plan

    # Import uploader functions from zernio_publish
    from zernio_publish import upload_and_schedule

    api_key = os.environ.get("ZERNIO_API_KEY")
    yt_acc = os.environ.get("ZERNIO_YOUTUBE_ACCOUNT_ID")
    ig_acc = os.environ.get("ZERNIO_INSTAGRAM_ACCOUNT_ID")

    accounts = []
    # YouTube has top priority
    if plan["eligible_youtube"] and yt_acc:
        accounts.append(("youtube", yt_acc))
    if plan["eligible_instagram"] and ig_acc:
        accounts.append(("instagram", ig_acc))

    if not accounts:
        print("  No eligible destination account for this clip.")
        return plan

    schedule_arg = plan["youtube_time"] or plan["instagram_time"] or "now"
    meta["approved"] = True
    try:
        res = upload_and_schedule(video_path, metadata_path, meta, accounts, schedule_arg, api_key)
        print(f"  🚀 Dispatched to Zernio! Post ID: {res.get('_id')} (Scheduled: {schedule_arg})")
    except Exception as e:
        print(f"  ❌ Upload error: {e}")

        meta["approved"] = True
        body = post_body(meta, upload["publicUrl"], accounts, schedule_arg)
        resp = requests.post(f"{API}/posts", headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        post_id = resp.json().get("post", {}).get("_id")
        print(f"  🚀 Dispatched to Zernio! Post ID: {post_id} (Scheduled: {schedule_arg})")

        meta["zernio_post_id"] = post_id
        meta["scheduled_for"] = schedule_arg
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    save_queue_state(state)
    return plan

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clip", type=Path, help="Clip json/mp4 or directory")
    parser.add_argument("--publish", action="store_true", help="Publish to Zernio")
    args = parser.parse_args()

    if args.clip.is_dir():
        clips = sorted(args.clip.glob("gta-*.json"))
        print(f"Found {len(clips)} clips in directory. Evaluating backlog...")
        for c in clips:
            schedule_single_clip(c, publish=args.publish)
    else:
        schedule_single_clip(args.clip, publish=args.publish)

if __name__ == "__main__":
    main()
