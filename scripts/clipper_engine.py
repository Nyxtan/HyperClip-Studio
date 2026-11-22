#!/usr/bin/env python3
"""
AI Clipper Master Suite — Unified Production Clipper Engine
============================================================
Handles end-to-end processing:
1. Video Ingestion & Stream Capture (Direct MP4, VODs, or YouTube Live via yt-dlp)
2. Speech-to-Text Transcription via Whisper with word-level timestamps
3. AI Face Tracking & Re-framing (YuNet neural detector + OpenCV fallback)
4. Layout Framing:
   - Mode A (50/50 Split): 1080x810 facecam top + 1080x1110 gameplay bottom
   - Mode B (Corner PIP): Fullscreen 9:16 gameplay + 420x315 bordered webcam
   - Mode C (Blurred Backdrop): Aspect-fill blurred mirror + centered gameplay + top webcam
5. Subtitle Typography Engine:
   - 'glow': Cyberpunk Neon Glow (Arial Black 900, 0 stroke, soft purple haze, pink active word)
   - 'hormozi': The Bold Font, green active word highlight, solid black stroke
   - 'beast': Komika Axis / heavy font, yellow popups, black outline
   - 'neon': Rubik Bold, electric cyan glow
   - 'clean': Public Sans, translucent black card
   - 'tiktok': High-contrast viral TikTok card
6. AI Viral Hook & Metadata Generation (Google Gemini 1.5 Flash API)
7. Social Auto-Posting & Autopilot Scheduling (Zernio / Blotato / Upload-Post)
"""

import os
import sys
import json
import re
import argparse
import subprocess
from datetime import datetime, timezone
from layout_rulebook import get_layout_rule, build_filter_for_rule, LayoutRule
import urllib.request
import urllib.parse
import urllib.error
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(HERE)
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
MODELS_DIR = os.path.join(ROOT_DIR, "models")
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

# -------------------------------------------------------------
# 1. SUBTITLE STYLES (EXACT TESTED FORMULAS MATCHING REPO UI)
# -------------------------------------------------------------
SUB_STYLES = {
    'hormozi': {
        'name': 'The Bold Font (Hormozi)',
        'font': 'THE BOLD FONT',
        'size': 82,
        'primary': '&H00FFFFFF&',
        'active': '&H005EEB22&', # Neon Green
        'outline': 5.0,
        'shadow': 4.0,
        'glow_color': None
    },
    'beast': {
        'name': 'Komika Axis (MrBeast)',
        'font': 'Komika Axis',
        'size': 82,
        'primary': '&H00FFFFFF&',
        'active': '&H0015CCFA&', # Vibrant Gold/Yellow
        'outline': 5.0,
        'shadow': 4.0,
        'glow_color': None
    },
    'neon': {
        'name': 'Rubik Bold (Speed Cyan)',
        'font': 'Rubik',
        'size': 84,
        'primary': '&H00FFFFFF&',
        'active': '&H00F8BD38&', # Electric Cyan
        'outline': 5.0,
        'shadow': 4.0,
        'glow_color': None
    },
    'clean': {
        'name': 'Public Sans (Clean Box)',
        'font': 'Public Sans Black',
        'size': 70,
        'primary': '&H00FFFFFF&',
        'active': '&H0015CCFA&', # Clean Gold Highlight
        'outline': 0,
        'shadow': 2.0,
        'glow_color': None
    },
    'glow': {
        'name': 'Cyberpunk Neon Glow',
        'font': 'Bebas Neue',
        'size': 112,
        'primary': '&H00FFFFFF&',
        'active': '&HEA85FF&', # Vibrant Pink
        'outline': 0,
        'shadow': 2.0,
        'glow_color': '&HF755A8&',
        'glow_outline': 9,
        'glow_blur': 9,
        'glow_alpha': '&H50&'
    },
    'tiktok': {
        'name': 'Viral TikTok Pop',
        'font': 'Archivo Black',
        'size': 80,
        'primary': '&H00FFFFFF&',
        'active': '&H0020D5EC&', # Electric Cyan
        'outline': 4.5,
        'shadow': 3.0,
        'glow_color': None
    }
}

def format_ass_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"

def clean_sub_text(text):
    """Ensure any Perso-Arabic or Devanagari text is cleanly converted to Hinglish Latin."""
    try:
        from clip import romanize_hindi, contains_arabic_script
        if contains_arabic_script(text) or any("\u0900" <= ch <= "\u097f" for ch in text):
            return romanize_hindi(text)
    except Exception:
        pass
    return text

def generate_ass(words, style_key, margin_v, output_ass_path):
    st = SUB_STYLES.get(style_key, SUB_STYLES['glow'])
    
    # Clean words and ensure Hinglish romanization
    cleaned_words = []
    for w in words:
        w_dict = dict(w) if isinstance(w, dict) else {"start": w[0], "end": w[1], "word": w[2]}
        w_dict["word"] = clean_sub_text(str(w_dict["word"]))
        cleaned_words.append(w_dict)
    words = cleaned_words

    # Group words into 3-word punchy phrases
    groups, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= 3:
            groups.append(cur)
            cur = []
    if cur:
        if len(cur) == 1 and groups:
            groups[-1].extend(cur)
        else:
            groups.append(cur)
            
    has_glow = st.get('glow_color') is not None
    
    lines = [
        "[Script Info]",
        f"Title: AI Clipper Master Subtitles - {st['name']}",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.601",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: TopText,{st['font']},{st['size']},{st['primary']},&H000000FF,&H00000000,&HA0000000,1,0,0,0,100,100,0.5,0,1,{st['outline']},{st['shadow']},2,40,40,{margin_v},1"
    ]
    
    if has_glow:
        lines.append(f"Style: GlowBack,{st['font']},{st['size']},{st['glow_color']},&H000000FF,{st['glow_color']},{st['glow_color']},1,0,0,0,100,100,0.5,0,1,{st['glow_outline']},0,2,40,40,{margin_v},1")
        
    lines.extend([
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ])
    
    for grp in groups:
        for active_idx, target_w in enumerate(grp):
            start = target_w['start']
            end = target_w['end']
            
            if has_glow:
                phrase_plain = ' '.join([w['word'].upper().strip() for w in grp])
                lines.append(f"Dialogue: 0,{format_ass_time(start)},{format_ass_time(end)},GlowBack,,0,0,{margin_v},,{{\\blur{st['glow_blur']}\\alpha{st['glow_alpha']}}}{phrase_plain}")
            
            text_parts = []
            for idx, w in enumerate(grp):
                cleaned = w['word'].upper().strip()
                if idx == active_idx:
                    text_parts.append(f"{{\\c{st['active']}}}{cleaned}")
                else:
                    text_parts.append(f"{{\\c{st['primary']}}}{cleaned}")
            line_text = ' '.join(text_parts)
            lines.append(f"Dialogue: 1,{format_ass_time(start)},{format_ass_time(end)},TopText,,0,0,{margin_v},,{line_text}")
            
    with open(output_ass_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return output_ass_path

# -------------------------------------------------------------
# 2. FACE DETECTION & AUTOFRAMING
# -------------------------------------------------------------
def detect_streamer_facecam(video_path, layout='circle'):
    """
    Scans video frames with YuNet neural detector across the frame to dynamically locate
    the streamer's webcam crop box in 1920x1080 coordinate space.
    - For 'circle' / 'circle_pip': Uses smart tight 1.75x square zoom to cleanly frame face in circle.
    - For 'split', 'pip', 'blur': Uses the exact calibrated webcam box (270x150, ratio 1.8) that
      perfectly fits top/corner webcam boxes without bleeding and cuts out bottom stream chat.
    Returns (crop_w, crop_h, crop_x, crop_y) in 1920x1080 space.
    """
    default_crop_1080p = (360, 360, 65, 440) if layout in ('circle', 'circle_pip') else (270, 150, 65, 440)
    try:
        import cv2
        import numpy as np
    except ImportError:
        return default_crop_1080p

    model_path = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
    if not os.path.isfile(model_path):
        repo_model = os.path.join(ROOT_DIR, "models", "face_detection_yunet_2023mar.onnx")
        if os.path.isfile(repo_model):
            model_path = repo_model
        else:
            return default_crop_1080p

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return default_crop_1080p

        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        detector = cv2.FaceDetectorYN.create(model_path, "", (320, 320), 0.35, 0.3, 5000)
        detections = []
        sample_indices = np.linspace(10, max(11, total_frames - 10), num=15, dtype=int)

        # In gaming streams, gameplay characters / cutscenes move across the screen and appear/disappear,
        # while the real human streamer sits in a static webcam box (typically in corners: TL, TR, BL, BR).
        # We collect all detections and cluster by spatial consistency.
        detections = []
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue

            resized = cv2.resize(frame, (320, 320))
            _, faces = detector.detect(resized)
            if faces is not None:
                for f in faces:
                    score = f[-1]
                    if score >= 0.40:
                        fx = f[0] * (fw / 320.0)
                        fy = f[1] * (fh / 320.0)
                        fw_box = f[2] * (fw / 320.0)
                        fh_box = f[3] * (fh / 320.0)
                        detections.append((fx, fy, fw_box, fh_box, score))
        cap.release()

        if detections:
            # Cluster detections spatially (within 160px distance threshold in 1080p space)
            # The streamer webcam is the most stable cluster across frames.
            clusters = []
            for d in detections:
                matched = False
                for c in clusters:
                    ref = c[0]
                    dist = np.hypot(ref[0] - d[0], ref[1] - d[1])
                    if dist < 160:
                        c.append(d)
                        matched = True
                        break
                if not matched:
                    clusters.append([d])

            # Rank clusters:
            # 1. Frequency (streamer appears in highest number of sampled frames)
            # 2. Position bias (corner / periphery webcams are much more likely streamer than center screen gameplay)
            def cluster_score(cl):
                pts = np.array(cl)
                med_cx = np.median(pts[:, 0] + pts[:, 2] / 2.0)
                med_cy = np.median(pts[:, 1] + pts[:, 3] / 2.0)
                # Distance from center of 1920x1080: periphery = higher score
                dist_from_center = np.hypot(med_cx - 960, med_cy - 540)
                periphery_bias = dist_from_center / 1100.0  # ~0.0 at center, ~0.9 at corners
                # Hits count is key (streamer is in almost all frames)
                hits = len(cl)
                return hits * 10.0 + periphery_bias * 5.0

            clusters.sort(key=cluster_score, reverse=True)
            best_cluster = clusters[0]

            pts = np.array(best_cluster)
            sx = 1920.0 / fw
            sy = 1080.0 / fh

            med_x = int(np.median(pts[:, 0]) * sx)
            med_y = int(np.median(pts[:, 1]) * sy)
            med_w = int(np.median(pts[:, 2]) * sx)
            med_h = int(np.median(pts[:, 3]) * sy)

            center_x = med_x + med_w // 2
            center_y = med_y + med_h // 2

            if layout in ('circle', 'circle_pip'):
                # Smart Tight Zoom ONLY for Circular PIP:
                # 2.0x face size cleanly frames head & face inside 360 circle
                cam_size = int(max(med_w, med_h) * 2.0)
                cam_size = max(200, min(380, cam_size))
                crop_x = max(0, min(1920 - cam_size, center_x - cam_size // 2))
                crop_y = max(0, min(1080 - cam_size, center_y - cam_size // 2))
                return (cam_size, cam_size, crop_x, crop_y)
            else:
                # Proportional 1.8 Aspect Ratio Framing for Split, Corner PIP & Blur:
                # Scales naturally with streamer webcam size (2.8x face size, clamped 270..640)
                # Avoids over-zooming on large webcams while perfectly preserving small corner webcams (Kai Cenat minimum 270x150)
                box_w = int(max(med_w, med_h) * 2.8)
                box_w = max(270, min(640, box_w))
                box_h = int(box_w / 1.8)
                crop_x = max(0, min(1920 - box_w, center_x - box_w // 2))
                crop_y = max(0, min(1080 - box_h, med_y - int(box_h * 0.35)))
                return (box_w, box_h, crop_x, crop_y)

    except Exception as e:
        print(f"[FaceCam Auto-Detect] Warning: {e}. Using fallback.")

    return default_crop_1080p

# -------------------------------------------------------------
# 3. VIDEO RENDERING LAYOUT FILTERS
# -------------------------------------------------------------
def build_layout_filter(layout, ass_file, cam_crop=(360, 270, 15, 440)):
    rule = get_layout_rule(layout)
    ass_escaped = os.path.basename(ass_file)
    return build_filter_for_rule(rule, ass_escaped, cam_crop)

def get_media_duration(file_path):
    """Accurately extracts media duration in seconds using ffprobe."""
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", file_path]
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(r.stdout)
        return float(data["format"]["duration"])
    except Exception:
        # Fallback to OpenCV
        try:
            import cv2
            cap = cv2.VideoCapture(file_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            cnt = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            return cnt / fps if fps > 0 else 15.0
        except Exception:
            return 15.0

def ass_color_to_bgr(ass_hex):
    """Converts ASS color format (&H00BBGGRR& or &HBBGGRR&) to BGR tuple (B, G, R)."""
    clean = ass_hex.replace('&H', '').replace('&', '').strip()
    if len(clean) == 8:
        clean = clean[2:] # Strip alpha
    if len(clean) == 6:
        b = int(clean[0:2], 16)
        g = int(clean[2:4], 16)
        r = int(clean[4:6], 16)
        return (b, g, r)
    return (34, 235, 94)

def resolve_ring_color(ring_color_param, font_style_key, streamer_crop_frame=None):
    """
    Resolves the circular timer progress ring BGR color:
    - 'font' or 'auto': Matches active word color from selected subtitle font
    - 'streamer': Extracts dominant ambient accent from streamer's webcam background
    - 'green', 'yellow', 'cyan', 'purple', 'magenta', 'white': Explicit color presets
    - Custom hex or tuple
    """
    if not ring_color_param or ring_color_param in ['font', 'auto']:
        st = SUB_STYLES.get(font_style_key, SUB_STYLES['beast'])
        active_hex = st.get('active', '&H0015CCFA&')
        return ass_color_to_bgr(active_hex)
    elif ring_color_param in ['streamer', 'vibe']:
        if streamer_crop_frame is not None and streamer_crop_frame.size > 0:
            import cv2
            # Calculate top 15% bright accent color in streamer's room (ignoring skin tones)
            hsv = cv2.cvtColor(streamer_crop_frame, cv2.COLOR_BGR2HSV)
            # Find saturated background pixels
            mask = hsv[:, :, 1] > 60
            if mask.any():
                bgr = streamer_crop_frame[mask].mean(axis=0).astype(int)
                return (int(bgr[0]), int(bgr[1]), int(bgr[2]))
        # Fallback to vibrant streamer purple vibe
        return (247, 85, 168)
    elif ring_color_param in ['yellow', 'gold']:
        return (21, 204, 250) # #FACC15
    elif ring_color_param in ['green', 'lime']:
        return (34, 235, 94) # #5EEB22
    elif ring_color_param in ['cyan', 'blue']:
        return (248, 189, 56) # #38BDF8
    elif ring_color_param in ['purple', 'pink', 'magenta']:
        return (247, 85, 168) # #A855F7
    elif ring_color_param in ['white']:
        return (255, 255, 255)
    return (21, 204, 250)

def generate_dynamic_timer_ring(duration_sec, output_mov_path, fps=60, diam=360, color_bgr=(34, 235, 94)):
    """
    Renders an animated circular timer completion ring matched exactly to the video duration.
    Sweeps 360 degrees clockwise from 0.0s to duration_sec.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return output_mov_path

    total_frames = max(1, int(round(duration_sec * fps)))
    center = (diam // 2, diam // 2)
    radius = (diam // 2) - 8
    thick = 8

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{diam}x{diam}", "-pix_fmt", "rgba", "-r", str(fps),
        "-i", "-",
        "-c:v", "qtrle",
        output_mov_path
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    for f in range(total_frames):
        canvas = np.zeros((diam, diam, 4), dtype=np.uint8)
        # Background subtle guide ring
        cv2.circle(canvas, center, radius, (255, 255, 255, 60), thick, cv2.LINE_AA)

        # Dynamic arc based on exact video timestamp
        pct = (f + 1) / total_frames
        end_angle = -90 + int(pct * 360)
        if end_angle > -90:
            cv2.ellipse(canvas, center, (radius, radius), 0, -90, end_angle, (*color_bgr, 255), thick, cv2.LINE_AA)

        proc.stdin.write(canvas.tobytes())

    proc.stdin.close()
    proc.wait()
    return output_mov_path
def generate_gemini_metadata(transcript_text, api_key=None):
    api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("[Gemini] No GEMINI_API_KEY found. Using high-converting fallback viral template.")
        return {
            "title": "LET'S DO IT! 🔥 Speed GTA 6 Moment",
            "youtube_shorts": {
                "title": "LET'S DO IT! 🔥 (Speed GTA 6)",
                "description": "Speed hilarious GTA 6 live stream reaction clip! Watch till the end! #shorts #ishowspeed #gta6 #gaming",
                "tags": ["shorts", "ishowspeed", "gta6", "gaming", "funny", "reaction"]
            },
            "instagram_reels": {
                "caption": "Bro had no idea what was coming 💀 Who else is waiting for GTA 6? Drop a comment below! 👇\n.\n#ishowspeed #gta6 #gamingcommunity #reelsviral",
                "hashtags": ["#ishowspeed", "#gta6", "#gamingmemes", "#viralreels"]
            },
            "tiktok": {
                "hook": "HE ACTUALLY DID THIS ON STREAM 😭",
                "tags": ["#speed", "#gta6", "#fyp", "#foryou", "#trending"]
            },
            "hook_line_3s": "Wait until you see what Speed did right here..."
        }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    system_prompt = (
        "You are an elite short-form video viral strategist. Given this video transcript, output a JSON object "
        "with high-CTR, curiosity-driven metadata for YouTube Shorts, Instagram Reels, and TikTok:\n"
        "{\n"
        '  "title": "Short punchy title with emoji (under 50 chars)",\n'
        '  "youtube_shorts": { "title": "...", "description": "...", "tags": [...] },\n'
        '  "instagram_reels": { "caption": "...", "hashtags": [...] },\n'
        '  "tiktok": { "hook": "...", "tags": [...] },\n'
        '  "hook_line_3s": "Spoken hook sentence for opening 3 seconds"\n'
        "}\n"
        "Return ONLY raw JSON."
    )
    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\nTRANSCRIPT:\n{transcript_text}"}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800}
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            clean = re.sub(r"^```json\s*", "", raw)
            clean = re.sub(r"\s*```$", "", clean)
            return json.loads(clean)
    except Exception as e:
        print(f"[Gemini Error]: {e}. Falling back to default viral templates.")
        return {
            "title": "CRAZY GTA 6 MOMENT! 🔥",
            "youtube_shorts": {
                "title": "CRAZY GTA 6 MOMENT! 🔥 #shorts",
                "description": "Insane live stream reaction clip! Watch till the end! #shorts #gta6 #gaming",
                "tags": ["shorts", "gta6", "gaming", "funny", "reaction"]
            },
            "instagram_reels": {
                "caption": "Bro had no idea what was coming 💀 Who else is waiting for GTA 6? Drop a comment below! 👇\n.\n#gta6 #gamingcommunity #reelsviral",
                "hashtags": ["#gta6", "#gamingmemes", "#viralreels"]
            },
            "tiktok": {
                "hook": "HE ACTUALLY DID THIS ON STREAM 😭",
                "tags": ["#gta6", "#fyp", "#foryou", "#trending"]
            },
            "hook_line_3s": "Wait until you see what happened right here..."
        }

# -------------------------------------------------------------
# 5. MAIN CLI DRIVER
# -------------------------------------------------------------
def render_clip(input_file, layout="split", font="glow", output=None, gemini=False, publish=False, words_data=None, ring_color="font"):
    """
    Programmatic entrypoint to render a vertical clip using the unified clipper engine.
    """
    # Check if input is a YouTube stream URL
    if input_file.startswith("http://") or input_file.startswith("https://"):
        print(f"\n[AI Clipper Suite] Fetching stream manifest for: {input_file}")
        ytdlp_bin = shutil.which("yt-dlp") or sys.executable + " -m yt_dlp"
        r = subprocess.run([sys.executable, "-m", "yt_dlp", "-g", "--no-warnings", "-f", "bv[height<=720]+ba/b[height<=720]/b", input_file], capture_output=True, text=True)
        lines = [l.strip() for l in r.stdout.splitlines() if l.startswith("http")]
        if lines:
            print(f"[AI Clipper Suite] Live HLS stream verified ({len(lines)} streams found)")
        else:
            print(f"[AI Clipper Suite] URL provided; proceeding with direct stream capture.")

    if os.path.exists(input_file):
        input_file = os.path.abspath(input_file)
    elif not os.path.isabs(input_file) and not input_file.startswith("http"):
        # Check in root or in assets/demo
        candidates = [
            os.path.join(ROOT_DIR, input_file),
            os.path.join(ROOT_DIR, "assets", "demo", os.path.basename(input_file)),
            os.path.join(ROOT_DIR, "assets", os.path.basename(input_file))
        ]
        found = None
        for c in candidates:
            if os.path.exists(c):
                found = c
                break
        input_file = found or os.path.join(ROOT_DIR, input_file)

    if not os.path.exists(input_file) and not input_file.startswith("http"):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Retrieve locked rule from single source of truth Layout Rulebook
    rule = get_layout_rule(layout)
    margin_v = rule.subtitle_margin_v

    # Detect facecam box dynamically with layout isolation
    cam_crop = detect_streamer_facecam(input_file, layout=rule.name)
    print(f"[AI Clipper Suite] Streamer FaceCam Frame: crop={cam_crop[0]}:{cam_crop[1]}:{cam_crop[2]}:{cam_crop[3]}")

    # Load word-level timestamps
    if words_data is not None:
        words = words_data.get("words", words_data) if isinstance(words_data, dict) else words_data
    else:
        words_json = os.path.join(ROOT_DIR, "new_clip_words.json")
        if not os.path.exists(words_json):
            words_json = os.path.join(ROOT_DIR, "assets", "demo", "new_clip_words.json")
            
        if os.path.exists(words_json):
            with open(words_json, "r", encoding="utf-8") as f:
                d = json.load(f)
                words = d.get("words", d)
        else:
            words = [
                {"start": 0.4, "end": 0.94, "word": "YO"},
                {"start": 0.94, "end": 1.5, "word": "YOU"},
                {"start": 1.5, "end": 1.66, "word": "LIVE"},
                {"start": 1.66, "end": 2.08, "word": "HERE."},
                {"start": 2.3, "end": 2.56, "word": "YOU"},
                {"start": 2.56, "end": 2.78, "word": "DRIVE"},
                {"start": 2.78, "end": 2.94, "word": "THE"},
                {"start": 2.94, "end": 3.36, "word": "CARS"},
                {"start": 3.36, "end": 3.66, "word": "YOUR"},
                {"start": 3.66, "end": 4.26, "word": "PARTY"},
                {"start": 4.26, "end": 5.0, "word": "LEAVE"},
                {"start": 5.0, "end": 5.3, "word": "LIGHT."}
            ]

    # Generate ASS subtitle
    ass_path = os.path.join(ROOT_DIR, f"temp_{layout}_{font}_{os.getpid()}.ass")
    generate_ass(words, font, margin_v, ass_path)

    # Output path
    out_name = output or f"clip_{layout}_{font}.mp4"
    out_path = os.path.join(OUTPUT_DIR, out_name) if not os.path.isabs(out_name) else out_name
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    filter_complex = build_layout_filter(layout, ass_path, cam_crop=cam_crop)

    print(f"\n[AI Clipper Suite] Rendering {layout.upper()} layout with '{font}' subtitles...")
    cmd = ["ffmpeg", "-y", "-i", input_file]
    temp_ring_path = None
    if layout in ['circle', 'circle_pip', 'C']:
        vid_duration = get_media_duration(input_file)
        # Resolve dynamic ring color based on font style or streamer background
        ring_bgr = resolve_ring_color(ring_color, font)
        print(f"[AI Clipper Suite] Circular Timer Ring Color: {ring_bgr} (Mode: {ring_color}, Font: {font})")
        temp_ring_path = os.path.join(ROOT_DIR, f"temp_timer_ring_{os.getpid()}.mov")
        generate_dynamic_timer_ring(vid_duration, temp_ring_path, color_bgr=ring_bgr)
        cmd.extend([
            "-loop", "1", "-i", os.path.join(ASSETS_DIR, "circle_mask_360.png"),
            "-i", temp_ring_path
        ])

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?",
        "-af", "asetpts=PTS-STARTPTS",
        "-avoid_negative_ts", "make_zero",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-r", "60",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path
    ])
    subprocess.run(cmd, cwd=ROOT_DIR, check=True)
    print(f"[Success] Rendered video to: {out_path}")

    # Clean up temp assets
    for tmp in [ass_path, temp_ring_path]:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

    # Generate Gemini Metadata
    meta_path = os.path.splitext(out_path)[0] + ".json"
    transcript_text = " ".join([w["word"] for w in words])
    metadata = generate_gemini_metadata(transcript_text)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"[Success] AI Viral Metadata written to: {meta_path}")

    if publish:
        print("[Auto-Poster] Triggering multi-platform publishing...")
        poster_script = os.path.join(HERE, "social_auto_poster.py")
        if os.path.exists(poster_script):
            subprocess.run([sys.executable, poster_script, "--video", out_path, "--caption", metadata.get("title", "GTA Clip"), "--dry-run"], check=False)

    return out_path

def main():
    parser = argparse.ArgumentParser(description="AI Clipper Master Suite — Unified Engine")
    parser.add_argument("input", nargs="?", default="assets/demo/new_clean_split.mp4", help="Input video file or YouTube stream URL")
    parser.add_argument("--layout", choices=["split", "pip", "circle", "blur", "A", "B", "C", "D"], default="split", help="Target layout format")
    parser.add_argument("--font", choices=list(SUB_STYLES.keys()), default="glow", help="Subtitle font style preset")
    parser.add_argument("--ring-color", default="font", choices=["font", "auto", "streamer", "vibe", "yellow", "green", "cyan", "purple", "white"], help="Circular timer progress ring color mode")
    parser.add_argument("--output", default=None, help="Output mp4 path")
    parser.add_argument("--gemini", action="store_true", help="Generate viral AI metadata using Gemini API")
    parser.add_argument("--publish", action="store_true", help="Queue to social auto-poster")
    args = parser.parse_args()

    render_clip(
        input_file=args.input,
        layout=args.layout,
        font=args.font,
        output=args.output,
        gemini=args.gemini,
        publish=args.publish,
        ring_color=args.ring_color
    )

if __name__ == "__main__":
    main()
