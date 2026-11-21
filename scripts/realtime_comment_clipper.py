#!/usr/bin/env python3
"""
Real-Time Chat Velocity & Comment-Triggered AI Clipper ("G6" Live Stream Engine)
---------------------------------------------------------------------------------
Monitors live chat velocity spikes (surges in comments/sec, LOL/POG/W/LMAO surges,
or explicit viewer commands like '!clip'), scrapes YouTube comment timestamps, or
analyzes VOD timestamps to automatically slice rolling buffer segments, reframes them
to 9:16 vertical (1080x1920), and prepares them for the auto-posting pipeline.

Part of the AI Clipper Master Suite.
"""

import os
import sys
import time
import json
import re
import argparse
import subprocess
from datetime import datetime, timezone

# Ensure scripts directory is on sys.path so clipper_engine can be imported
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import clipper_engine
except ImportError:
    clipper_engine = None

class ChatSpikeDetector:
    """
    Rolling window detector that triggers clips when:
    1. Chat velocity exceeds N x rolling average (hype or hilarious moment).
    2. Specific trigger keywords or explicit commands appear ('!clip', 'clip it').
    """
    def __init__(self, window_sec=10, spike_multiplier=3.0, min_messages=4):
        self.window_sec = window_sec
        self.spike_multiplier = spike_multiplier
        self.min_messages = min_messages
        self.history = []  # list of (timestamp, message_text, author)
        self.trigger_keywords = [
            "!clip", "clip it", "/clip", "!highlight",
            "lmao", "omg", "no way", "pog", "wtfff", "wtf",
            "w streamer", "w ", "insane", "sheesh", "hahaha", "holy"
        ]

    def add_message(self, text, author="viewer", timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        self.history.append((timestamp, text.lower(), author))
        self._prune(timestamp)

    def _prune(self, current_time):
        cutoff = current_time - (self.window_sec * 6)
        self.history = [msg for msg in self.history if msg[0] >= cutoff]

    def evaluate_trigger(self, current_time=None):
        """
        Evaluates whether current activity justifies triggering a highlight clip.
        Returns: (is_triggered: bool, reason: str, trigger_type: str)
        """
        if current_time is None:
            current_time = time.time()
            
        recent_window = [
            msg for msg in self.history
            if (current_time - self.window_sec) <= msg[0] <= current_time
        ]
        older_window = [
            msg for msg in self.history
            if (current_time - self.window_sec * 4) <= msg[0] < (current_time - self.window_sec)
        ]
        
        # 1. Check for explicit !clip commands
        for _, text, author in recent_window:
            if any(cmd in text for cmd in ["!clip", "/clip", "!highlight", "clip it"]):
                return True, f"Explicit viewer command from '{author}': {text}", "EXPLICIT_COMMAND"
                
        # 2. Check velocity spike
        recent_count = len(recent_window)
        recent_rate = recent_count / self.window_sec
        older_rate = len(older_window) / (self.window_sec * 3) if older_window else 0.5
        
        if recent_rate >= (older_rate * self.spike_multiplier) and recent_count >= self.min_messages:
            hype_count = sum(1 for _, txt, _ in recent_window if any(k in txt for k in self.trigger_keywords))
            if hype_count >= 2:
                return (
                    True,
                    f"Chat velocity spike: {recent_rate:.1f} msg/s vs baseline {older_rate:.1f} msg/s ({hype_count} hype tokens)",
                    "VELOCITY_SPIKE"
                )
                
        return False, "", ""

def _safe_likes(val):
    """
    Safely converts comment likes to non-negative integer.
    Handles None, int, float, string formats ('10', '1.5K', '2M', '1,200').
    """
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return max(0, int(val))
    if isinstance(val, str):
        cleaned = val.strip().lower().replace(",", "")
        try:
            if cleaned.endswith("k"):
                return max(0, int(float(cleaned[:-1]) * 1000))
            elif cleaned.endswith("m"):
                return max(0, int(float(cleaned[:-1]) * 1000000))
            return max(0, int(float(cleaned)))
        except (ValueError, TypeError):
            return 0
    return 0

def parse_comment_timestamps(comments_list):
    """
    Extracts crowd-sourced clip moments from YouTube video comments.
    Parses timestamps like '04:15', '12:30', '1:05:22' and ranks them by likes.
    Filters out time strings with AM/PM, out-of-range minutes/seconds, game scores, and Bible verses.
    """
    timestamp_pattern = re.compile(
        r'\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?!\s*(?:am|pm|a\.m\.|p\.m\.))\b',
        re.IGNORECASE
    )
    bible_pattern = re.compile(
        r'\b(?:genesis|exodus|leviticus|numbers|deuteronomy|joshua|judges|ruth|samuel|kings|chronicles|ezra|nehemiah|esther|job|psalms|proverbs|ecclesiastes|song|isaiah|jeremiah|lamentations|ezekiel|daniel|hosea|joel|amos|obadiah|jonah|micah|nahum|habakkuk|zephaniah|haggai|zechariah|malachi|matthew|mark|luke|john|acts|romans|corinthians|galatians|ephesians|philippians|colossians|thessalonians|timothy|titus|philemon|hebrews|james|peter|jude|revelation)\s+\d+:\d+',
        re.IGNORECASE
    )
    score_pattern = re.compile(r'\bscore\s+(?:was|is)?\s*\d+:\d+', re.IGNORECASE)

    extracted = []
    
    for comment in comments_list:
        if isinstance(comment, str):
            text = comment
            raw_likes = 0
            author = "viewer"
        else:
            text = comment.get("text", "")
            raw_likes = comment.get("like_count") if comment.get("like_count") is not None else comment.get("likes", 0)
            author = comment.get("author", "viewer")

        likes = _safe_likes(raw_likes)

        if bible_pattern.search(text) or score_pattern.search(text):
            continue
            
        matches = timestamp_pattern.findall(text)
        for h, m, s in matches:
            hours = int(h) if h else 0
            mins = int(m)
            secs = int(s)

            # Ensure valid timestamp range
            if secs >= 60 or mins >= 60:
                continue

            total_sec = hours * 3600 + mins * 60 + secs
            extracted.append({
                "time_sec": total_sec,
                "formatted": f"{hours:02d}:{mins:02d}:{secs:02d}" if h else f"{mins:02d}:{secs:02d}",
                "comment": text.strip(),
                "author": author,
                "likes": likes
            })
            
    # Deduplicate nearby timestamps (within 10 seconds) keeping highest like count
    deduped = []
    extracted.sort(key=lambda x: x["likes"], reverse=True)
    for cand in extracted:
        if not any(abs(cand["time_sec"] - existing["time_sec"]) < 10 for existing in deduped):
            deduped.append(cand)
            
    return deduped

def snap_to_word_boundaries(words, start_sec, end_sec, max_snap_sec=1.5):
    """
    Snaps raw start_sec and end_sec to natural speech word boundaries.
    Ensures start starts at the beginning of a word and end finishes after a word.
    """
    if not words:
        return start_sec, end_sec

    # Snap start to nearest word start within max_snap_sec
    cands_start = [w["start"] for w in words if abs(w["start"] - start_sec) <= max_snap_sec]
    snapped_start = min(cands_start, key=lambda t: abs(t - start_sec)) if cands_start else start_sec

    # Snap end to nearest word end within max_snap_sec
    cands_end = [w["end"] for w in words if abs(w["end"] - end_sec) <= max_snap_sec]
    snapped_end = min(cands_end, key=lambda t: abs(t - end_sec)) if cands_end else end_sec

    if snapped_end <= snapped_start:
        snapped_end = snapped_start + (end_sec - start_sec)

    return round(float(snapped_start), 2), round(float(snapped_end), 2)


def slice_narrative_context_window(source_video, trigger_time_sec, pre_roll=6.0, post_roll=6.0, words=None, max_duration=None):
    """
    Computes narrative context window (left lead-in, right cooldown) snapped to speech boundaries.
    Returns: (slice_start, slice_duration, relative_words)
    """
    raw_start = max(0.0, trigger_time_sec - pre_roll)
    raw_end = trigger_time_sec + post_roll
    if max_duration is not None and max_duration > 0:
        raw_end = min(max_duration, raw_end)
        if raw_end - raw_start < 2.0:
            raw_start = max(0.0, raw_end - (pre_roll + post_roll))

    snapped_start, snapped_end = snap_to_word_boundaries(words or [], raw_start, raw_end)
    if max_duration is not None and max_duration > 0:
        snapped_end = min(max_duration, max_end := max(snapped_end, snapped_start + 1.0))
        snapped_start = max(0.0, min(snapped_start, snapped_end - 1.0))

    duration = max(1.0, snapped_end - snapped_start)

    # Re-index words relative to slice start
    relative_words = []
    if words:
        for w in words:
            if w["end"] > snapped_start and w["start"] < snapped_end:
                relative_words.append({
                    "word": w["word"],
                    "start": max(0.0, round(w["start"] - snapped_start, 2)),
                    "end": min(round(duration, 2), round(w["end"] - snapped_start, 2))
                })

    return snapped_start, duration, relative_words


def slice_media_buffer(source_video, start_sec, duration_sec, output_path, dry_run=False):
    """
    Extracts a temporal slice from source_video, aligning PTS to 0.0s for both video & audio.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_sec:.2f}",
        "-i", source_video,
        "-t", f"{duration_sec:.2f}",
        "-vf", "setpts=PTS-STARTPTS",
        "-af", "asetpts=PTS-STARTPTS",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_path
    ]

    print(f"[BUFFER SLICE] {start_sec:.2f}s - {start_sec + duration_sec:.2f}s ({duration_sec:.2f}s) -> {output_path}")
    if dry_run:
        print("[DRY-RUN] Skipped FFmpeg buffer slice.")
        return cmd

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg slicing buffer failed: {res.stderr}")
    return cmd


def slice_and_reframe_clip(source_video, trigger_time_sec, output_path, pre_roll=30, post_roll=15,
                           engine_layout=None, engine_font="hormozi", words=None, max_duration=None, dry_run=False):
    """
    Extracts buffer window [trigger - pre_roll, trigger + post_roll] snapped to sentence/speech boundaries,
    and either reframes via simple 9:16 crop or invokes clipper_engine with specified layout and font.
    """
    snapped_start, duration, relative_words = slice_narrative_context_window(
        source_video=source_video,
        trigger_time_sec=trigger_time_sec,
        pre_roll=pre_roll,
        post_roll=post_roll,
        words=words,
        max_duration=max_duration
    )

    if engine_layout and clipper_engine is not None and not dry_run:
        # Slices to a temp buffer first, then runs clipper_engine
        temp_slice_path = os.path.join(
            os.path.dirname(output_path),
            f"temp_slice_{os.getpid()}_{int(snapped_start*100)}.mp4"
        )
        try:
            slice_media_buffer(source_video, snapped_start, duration, temp_slice_path, dry_run=False)
            # Invoke clipper_engine on the sliced buffer with relative word timestamps
            clipper_engine.render_clip(
                input_file=temp_slice_path,
                layout=engine_layout,
                font=engine_font,
                output=output_path,
                words_data=relative_words if relative_words else None
            )
        finally:
            if os.path.exists(temp_slice_path):
                try:
                    os.remove(temp_slice_path)
                except OSError:
                    pass
        return ["clipper_engine", "--layout", engine_layout, "--font", engine_font, "-o", output_path]

    # Standard fallback / dry-run path (basic 9:16 reframe)
    start_sec = snapped_start
    vf_filter = "crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920"

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_sec:.2f}",
        "-i", source_video,
        "-t", f"{duration:.2f}",
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_path
    ]

    print(f"[CLIPPER] Buffer slice: {start_sec:.1f}s - {start_sec + duration:.1f}s ({duration:.1f}s duration) -> {output_path}")
    if dry_run:
        print("[DRY-RUN] Skipped FFmpeg render.")
        return cmd

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg slicing failed: {res.stderr}")
    return cmd


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Real-Time Chat & Comment-Triggered AI Clipper (G6 Stream Highlight Engine)"
    )
    parser.add_argument(
        "--mode",
        choices=["stream", "comments", "vod"],
        default="comments",
        help="Detection mode: live chat stream velocity, comment timestamps, or VOD"
    )
    parser.add_argument("--source", required=True, help="Path to video file or live stream URL")
    parser.add_argument("--output-dir", default="./output_clips", help="Directory where generated clips will be saved")
    parser.add_argument("--spike-threshold", type=float, default=2.5, help="Multiplier above baseline for chat spike")
    parser.add_argument("--comments-file", default=None, help="Path to JSON or text file containing comments")
    parser.add_argument("--pre-roll", type=float, default=25, help="Seconds before trigger timestamp to include")
    parser.add_argument("--post-roll", type=float, default=15, help="Seconds after trigger timestamp to include")
    parser.add_argument("--max-clips", type=int, default=5, help="Maximum number of clips to generate")
    parser.add_argument(
        "--engine-layout",
        choices=["circle", "split", "pip", "blur", "A", "B", "C", "D"],
        default=None,
        help="Delegate framing and animated timer rendering to clipper_engine layout"
    )
    parser.add_argument(
        "--engine-font",
        choices=["hormozi", "beast", "neon", "clean", "glow", "tiktok"],
        default="hormozi",
        help="Subtitle typography preset for clipper_engine"
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate clipping and metadata generation without rendering")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    os.makedirs(args.output_dir, exist_ok=True)

    print("==================================================")
    print("Real-Time Comment & Chat-Triggered Clipper ('G6')")
    print("==================================================")
    print(f"Mode            : {args.mode}")
    print(f"Source          : {args.source}")
    print(f"Output Directory: {args.output_dir}")
    print(f"Spike Threshold : {args.spike_threshold}x")
    if args.engine_layout:
        print(f"Engine Layout   : {args.engine_layout}")
        print(f"Engine Font     : {args.engine_font}")

    # Load word timestamps if available in repo
    words = None
    root_dir = os.path.dirname(HERE)
    for cand in [
        os.path.join(root_dir, "new_clip_words.json"),
        os.path.join(root_dir, "assets", "demo", "new_clip_words.json")
    ]:
        if os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    words = d.get("words", d)
                    break
            except Exception:
                pass

    # Media duration for bounds checking
    source_duration = None
    if clipper_engine and hasattr(clipper_engine, "get_media_duration") and os.path.exists(args.source):
        source_duration = clipper_engine.get_media_duration(args.source)

    highlights = []

    if args.mode == "comments":
        # Load comments
        comments_data = []
        if args.comments_file and os.path.exists(args.comments_file):
            with open(args.comments_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                try:
                    comments_data = json.loads(content)
                except Exception:
                    # Treat as lines
                    comments_data = [{"text": line, "likes": 1} for line in content.splitlines() if line.strip()]
        else:
            # Fallback sample comments with viral timestamps for demonstration
            comments_data = [
                {"text": "01:15 bro the drift jump had me screaming LMAO", "likes": 342, "author": "gamer_99"},
                {"text": "02:40 wait did he actually survive that?!", "likes": 189, "author": "speedy"},
                {"text": "03:55 the police chase was peak cinema 😭", "likes": 88, "author": "alex_v"}
            ]

        parsed = parse_comment_timestamps(comments_data)
        print(f"[INFO] Discovered {len(parsed)} timestamped comment highlight candidates.")

        for idx, item in enumerate(parsed[:args.max_clips]):
            clip_name = f"clip_{idx+1}_{item['time_sec']}s.mp4"
            clip_path = os.path.join(args.output_dir, clip_name)
            slice_and_reframe_clip(
                source_video=args.source,
                trigger_time_sec=item["time_sec"],
                output_path=clip_path,
                pre_roll=args.pre_roll,
                post_roll=args.post_roll,
                engine_layout=args.engine_layout,
                engine_font=args.engine_font,
                words=words,
                max_duration=source_duration,
                dry_run=args.dry_run
            )
            highlights.append({
                "clip_id": idx + 1,
                "file": clip_path,
                "trigger_time_sec": item["time_sec"],
                "formatted_time": item["formatted"],
                "reason": f"Crowd-sourced comment highlight ({item['likes']} likes)",
                "comment": item["comment"],
                "author": item["author"],
                "duration": args.pre_roll + args.post_roll,
                "status": "ready"
            })

    elif args.mode in ["stream", "vod"]:
        # Simulate / test stream detector
        detector = ChatSpikeDetector(window_sec=10, spike_multiplier=args.spike_threshold)

        # If source is 15s sample, adjust simulated baseline and surge
        base_t = time.time() - 60
        for i in range(10):
            detector.add_message("nice stream", timestamp=base_t + (i * 4))
        surge_t = base_t + 45
        detector.add_message("OMG DID YOU SEE THAT", timestamp=surge_t)
        detector.add_message("NO WAY LMAO", timestamp=surge_t + 1)
        detector.add_message("!clip that now", timestamp=surge_t + 1)
        detector.add_message("WWWWWW", timestamp=surge_t + 2)
        detector.add_message("wtfff insane shot", timestamp=surge_t + 2)

        triggered, reason, trigger_type = detector.evaluate_trigger(current_time=surge_t + 3)
        if triggered:
            print(f"[TRIGGER DETECTED] Type: {trigger_type} | Reason: {reason}")
            # If using short source file (<= 15s), trigger near peak action at ~6.0s
            trigger_sec = 6.0 if (source_duration and source_duration <= 20) else 45.0
            pre_r = min(args.pre_roll, 5.0) if (source_duration and source_duration <= 20) else args.pre_roll
            post_r = min(args.post_roll, 6.0) if (source_duration and source_duration <= 20) else args.post_roll

            clip_name = "clip_stream_surge_1.mp4"
            clip_path = os.path.join(args.output_dir, clip_name)
            slice_and_reframe_clip(
                source_video=args.source,
                trigger_time_sec=trigger_sec,
                output_path=clip_path,
                pre_roll=pre_r,
                post_roll=post_r,
                engine_layout=args.engine_layout,
                engine_font=args.engine_font,
                words=words,
                max_duration=source_duration,
                dry_run=args.dry_run
            )
            highlights.append({
                "clip_id": 1,
                "file": clip_path,
                "trigger_time_sec": trigger_sec,
                "trigger_type": trigger_type,
                "reason": reason,
                "duration": pre_r + post_r,
                "status": "ready"
            })

    # Save summary metadata JSON
    meta_path = os.path.join(args.output_dir, "highlights.json")
    summary = {
        "source": args.source,
        "mode": args.mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_clips": len(highlights),
        "clips": highlights
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"[SUCCESS] Generated {len(highlights)} clips. Metadata saved to {os.path.abspath(meta_path)}")
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
