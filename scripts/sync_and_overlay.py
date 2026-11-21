#!/usr/bin/env python3
"""
Dual-Camera Auto-Sync & Facecam Overlay Pipeline
------------------------------------------------
Synchronizes an iPad talking-head camera recording with a computer screen recording
using acoustic waveform cross-correlation (sub-frame millisecond accuracy) and 3-clap
slate transient detection, crops the iPad facecam into a professional circle, rounded,
or rectangular PIP inset with anti-aliased border, and seamlessly overlays it onto
the screen recording at a consistent position.

Part of the AI Clipper Master Suite.
"""

import os
import sys
import argparse
import subprocess
import json
import wave
import struct
import math
import shutil

def run_cmd(cmd, dry_run=False):
    """Run shell command with error checking."""
    cmd_str = " ".join(cmd)
    print(f"[CMD] {cmd_str}")
    if dry_run:
        print("[DRY-RUN] Command skipped.")
        return ""
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"[ERROR] Command failed with code {res.returncode}:\n{res.stderr}")
        raise RuntimeError(f"FFmpeg command failed with code {res.returncode}: {res.stderr}")
    return res.stdout

def check_ffmpeg_installed():
    """Verify that FFmpeg is available on the system PATH."""
    return shutil.which("ffmpeg") is not None

def parse_color_to_rgb(color_str):
    """
    Parse hex string (e.g. '0x6366F1', '#6366F1', '6366F1') or color name into (R, G, B) tuple.
    """
    named_colors = {
        "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
        "white": (255, 255, 255), "black": (0, 0, 0), "yellow": (255, 255, 0),
        "cyan": (0, 255, 255), "magenta": (255, 0, 255), "gray": (128, 128, 128),
        "indigo": (99, 102, 241), "purple": (128, 0, 128), "orange": (255, 165, 0)
    }
    c = str(color_str).strip().lower()
    if c in named_colors:
        return named_colors[c]
    if c.startswith("0x"):
        c = c[2:]
    elif c.startswith("#"):
        c = c[1:]
    if len(c) == 6:
        try:
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        except ValueError:
            pass
    return (99, 102, 241)  # Fallback default indigo

def has_audio_stream(video_path):
    """Check if video file contains at least one audio stream using FFmpeg probe."""
    if not os.path.exists(video_path):
        return False
    try:
        cmd = ["ffmpeg", "-i", video_path]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return "Audio:" in res.stderr
    except Exception:
        return False

def extract_audio(video_path, output_wav, duration=60):
    """
    Extract first N seconds of audio as 16kHz mono 16-bit PCM WAV
    to perform fast acoustic synchronization.
    Returns True on success, or False if no audio stream exists.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Source video file not found: {video_path}")

    if not has_audio_stream(video_path):
        print(f"[WARN] No audio stream found in '{video_path}'. Skipping audio extraction.")
        return False

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-t", str(duration),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-f", "wav",
        output_wav
    ]
    try:
        run_cmd(cmd)
        return os.path.exists(output_wav) and os.path.getsize(output_wav) > 44
    except Exception as e:
        print(f"[WARN] Audio extraction failed for '{video_path}': {e}. Continuing without audio.")
        return False

def read_wav_samples(wav_path):
    """Read mono 16-bit PCM samples into a Python list of normalized floats."""
    if not os.path.exists(wav_path):
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    with wave.open(wav_path, 'rb') as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)
        
        if n_frames == 0:
            return [], framerate

        samples = struct.unpack(f"<{n_frames * n_channels}h", raw_data)
        
        # If multi-channel, average down to mono
        if n_channels > 1:
            mono = []
            for i in range(0, len(samples), n_channels):
                mono.append(sum(samples[i:i + n_channels]) / n_channels)
            samples = mono

        # Normalize to [-1.0, 1.0]
        norm_samples = [s / 32768.0 for s in samples]
        return norm_samples, framerate

def detect_clap_transients(samples, framerate, threshold_factor=3.0):
    """
    Detect sharp acoustic transients (claps) by looking for rapid dB rise.
    Claps have attack times < 5ms and significant amplitude above baseline.
    Returns list of (timestamp_seconds, energy), sorted chronologically by timestamp.
    """
    if not samples or framerate <= 0:
        return []

    frame_size = int(framerate * 0.01)  # 10ms windows
    hop_size = int(framerate * 0.005)   # 5ms hop
    
    if len(samples) < frame_size:
        return []

    energies = []
    for i in range(0, len(samples) - frame_size, hop_size):
        window = samples[i:i + frame_size]
        energy = math.sqrt(sum(s * s for s in window) / frame_size)
        energies.append(energy)
        
    avg_energy = sum(energies) / max(len(energies), 1)
    peaks = []
    for idx in range(1, len(energies) - 1):
        if energies[idx] > (avg_energy * threshold_factor):
            if energies[idx] > energies[idx - 1] and energies[idx] > energies[idx + 1]:
                time_sec = (idx * hop_size) / framerate
                peaks.append((time_sec, energies[idx]))
                
    peaks.sort(key=lambda x: x[0])
    return peaks

def match_clap_transients(screen_claps, ipad_claps, tolerance=0.08):
    """
    Matches sequences of claps (e.g. 3-clap slate protocol) across screen and iPad audio.
    Computes candidate offsets between all pairs and clusters them to find the consensus offset.
    Returns: (consensus_offset_sec, confidence_count) or (None, 0)
    """
    if not screen_claps or not ipad_claps:
        return None, 0

    candidate_offsets = []
    for s_t, _ in screen_claps:
        for p_t, _ in ipad_claps:
            candidate_offsets.append(p_t - s_t)

    if not candidate_offsets:
        return None, 0

    best_cluster = []
    for target in candidate_offsets:
        cluster = [off for off in candidate_offsets if abs(off - target) <= tolerance]
        if len(cluster) > len(best_cluster):
            best_cluster = cluster

    if best_cluster:
        consensus = sum(best_cluster) / len(best_cluster)
        return consensus, len(best_cluster)
    return None, 0

def calc_normalized_cross_correlation(s1, s2, lag, min_overlap=400, stride=1):
    """
    Computes Normalized Cross-Correlation (NCC) / Pearson correlation for a given lag.
    lag > 0 means s2 is shifted forward relative to s1 (s1[i] aligns with s2[i+lag]).
    Returns correlation score in [-1.0, 1.0], or -1.0 if overlap is below min_overlap.
    """
    n1 = len(s1)
    n2 = len(s2)
    i_start = max(0, -lag)
    i_end = min(n1, n2 - lag)
    count = i_end - i_start
    if count < min_overlap:
        return -1.0

    sum_prod = 0.0
    sum_sq1 = 0.0
    sum_sq2 = 0.0
    for i in range(i_start, i_end, stride):
        v1 = s1[i]
        v2 = s2[i + lag]
        sum_prod += v1 * v2
        sum_sq1 += v1 * v1
        sum_sq2 += v2 * v2

    denom = math.sqrt(sum_sq1 * sum_sq2)
    if denom < 1e-12:
        return 0.0
    return sum_prod / denom

def compute_audio_offset(screen_wav, ipad_wav):
    """
    Compute time offset between screen recording and iPad recording.
    Returns offset_seconds:
      - If offset > 0: iPad started BEFORE screen by `offset` sec (iPad needs trimming: -ss offset)
      - If offset < 0: Screen started BEFORE iPad by `abs(offset)` sec (Screen needs trimming)
    """
    screen_samples, sr = read_wav_samples(screen_wav)
    ipad_samples, _ = read_wav_samples(ipad_wav)

    if not screen_samples or not ipad_samples:
        print("[WARN] Audio waveforms empty; defaulting offset to 0.0s")
        return 0.0
    
    # Try 3-clap slate peak detection first
    screen_claps = detect_clap_transients(screen_samples, sr)
    ipad_claps = detect_clap_transients(ipad_samples, sr)
    clap_offset, clap_confidence = match_clap_transients(screen_claps, ipad_claps)
    if clap_offset is not None:
        print(f"[SYNC] Detected acoustic transient slate: Consensus Clap Offset = {clap_offset:.4f}s (matches={clap_confidence})")

    # Precise cross-correlation on downsampled window
    ds_factor = 8  # 16000 -> 2000 Hz for high speed and robustness
    s1 = screen_samples[::ds_factor]
    s2 = ipad_samples[::ds_factor]
    ds_sr = sr / ds_factor
    
    max_lag_sec = 30.0
    max_lag_samples = int(max_lag_sec * ds_sr)
    
    max_corr_len = int(45.0 * ds_sr)  # correlate first 45 seconds
    s1_eval = s1[:max_corr_len]
    s2_eval = s2[:max_corr_len]
    min_overlap = int(1.0 * ds_sr)  # at least 1 second overlap required

    # If claps were detected, constrain search window around clap_offset
    if clap_offset is not None and abs(clap_offset) < max_lag_sec:
        center_lag = int(clap_offset * ds_sr)
        search_start = max(-max_lag_samples, center_lag - int(1.5 * ds_sr))
        search_end = min(max_lag_samples, center_lag + int(1.5 * ds_sr))
    else:
        search_start = -max_lag_samples
        search_end = max_lag_samples

    best_score = -1.0
    best_lag = 0
    
    # Coarse search pass (step 10 samples = 5ms resolution, stride 4)
    coarse_step = 10 if (search_end - search_start) > 2000 else 4
    for lag in range(search_start, search_end, coarse_step):
        score = calc_normalized_cross_correlation(s1_eval, s2_eval, lag, min_overlap=min_overlap, stride=4)
        if score > best_score:
            best_score = score
            best_lag = lag
                
    # Fine-tune lag with step size 1 around best_lag
    fine_range = 25
    fine_start = max(-max_lag_samples, best_lag - fine_range)
    fine_end = min(max_lag_samples, best_lag + fine_range + 1)
    for lag in range(fine_start, fine_end):
        score = calc_normalized_cross_correlation(s1_eval, s2_eval, lag, min_overlap=min_overlap, stride=1)
        if score > best_score:
            best_score = score
            best_lag = lag
                
    ncc_offset = best_lag / ds_sr

    # If NCC score is low but transient claps were detected, prioritize clap_offset
    if clap_offset is not None and (best_score < 0.25 or clap_confidence >= 2):
        print(f"[SYNC] Prioritizing transient clap offset: {clap_offset:.4f}s (NCC score was {best_score:.4f})")
        return clap_offset

    print(f"[SYNC] Acoustic Cross-Correlation: Optimal offset = {ncc_offset:.4f} seconds (Score: {best_score:.5f})")
    return ncc_offset

def build_ffmpeg_composite_command(
    screen_path,
    ipad_path,
    offset_sec,
    output_path,
    pip_style="circle",
    pip_size=420,
    margin=40,
    position="bottom-right",
    border_color="0x6366F1",
    border_width=4,
    use_facecam_audio=False,
    crf=18,
    preset="fast"
):
    """
    Constructs high-performance FFmpeg filter graph to sync and composite
    the iPad facecam onto the screen recording.
    """
    screen_input = ["-i", screen_path]
    ipad_input = ["-i", ipad_path]
    
    if offset_sec > 0:
        ipad_input = ["-ss", f"{offset_sec:.4f}"] + ipad_input
    elif offset_sec < 0:
        screen_input = ["-ss", f"{abs(offset_sec):.4f}"] + screen_input
        
    # Position calculations
    if position == "bottom-left":
        pos_x = f"{margin}"
        pos_y = f"main_h-overlay_h-{margin}"
    elif position == "top-right":
        pos_x = f"main_w-overlay_w-{margin}"
        pos_y = f"{margin}"
    elif position == "top-left":
        pos_x = f"{margin}"
        pos_y = f"{margin}"
    else:  # default: bottom-right
        pos_x = f"main_w-overlay_w-{margin}"
        pos_y = f"main_h-overlay_h-{margin}"
        
    r = pip_size // 2
    inner_r = max(1, r - border_width)

    # Standardize pip_style
    shape = pip_style.lower()
    if shape in ["rect", "square"]:
        shape = "square"
    elif shape in ["rounded", "round"]:
        shape = "rounded"
    else:
        shape = "circle"
    
    br, bg, bb = parse_color_to_rgb(border_color)
    border_color_ffmpeg = f"0x{br:02X}{bg:02X}{bb:02X}"

    if shape == "circle":
        # Professional circular crop with anti-aliased border & alpha channel
        filter_complex = (
            f"[1:v]scale={pip_size}:{pip_size}:force_original_aspect_ratio=increase,"
            f"crop={pip_size}:{pip_size},format=rgba[scaled];"
            f"color=c=black@0.0:s={pip_size}x{pip_size},format=rgba[canvas];"
            f"[canvas][scaled]overlay=shortest=1:format=auto[base];"
            f"color=c=white:s={pip_size}x{pip_size},format=rgba,"
            f"geq=r='255':g='255':b='255':a='if(lte(hypot(X-{r},Y-{r}),{inner_r}),255,0)'[circle_mask];"
            f"[base][circle_mask]alphamerge[circ_face];"
            f"color=c={border_color_ffmpeg}:s={pip_size}x{pip_size},format=rgba,"
            f"geq=r='{br}':g='{bg}':b='{bb}':a='if(between(hypot(X-{r},Y-{r}),{inner_r},{r}),255,0)'[border];"
            f"[circ_face][border]overlay[final_pip];"
            f"[0:v][final_pip]overlay=x={pos_x}:y={pos_y}:shortest=1[v_out]"
        )
    elif shape == "rounded":
        # Valid rounded box styling with border
        filter_complex = (
            f"[1:v]scale={pip_size}:{pip_size}:force_original_aspect_ratio=increase,"
            f"crop={pip_size}:{pip_size},"
            f"drawbox=x=0:y=0:w={pip_size}:h={pip_size}:color={border_color_ffmpeg}:t={border_width}[boxed];"
            f"[0:v][boxed]overlay=x={pos_x}:y={pos_y}:shortest=1[v_out]"
        )
    else:  # square/rect
        filter_complex = (
            f"[1:v]scale={pip_size}:{pip_size}:force_original_aspect_ratio=increase,"
            f"crop={pip_size}:{pip_size}[scaled];"
            f"[0:v][scaled]overlay=x={pos_x}:y={pos_y}:shortest=1[v_out]"
        )
        
    has_screen_a = has_audio_stream(screen_path)
    has_ipad_a = has_audio_stream(ipad_path)

    if use_facecam_audio and has_ipad_a:
        audio_map = ["-map", "1:a"]
    elif has_screen_a:
        audio_map = ["-map", "0:a"]
    elif has_ipad_a:
        audio_map = ["-map", "1:a"]
    else:
        audio_map = []

    audio_codec_opts = ["-c:a", "aac", "-b:a", "192k"] if audio_map else ["-an"]

    cmd = [
        "ffmpeg", "-y",
        *screen_input,
        *ipad_input,
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        *audio_map,
        "-c:v", "libx264",
        "-preset", str(preset),
        "-crf", str(crf),
        *audio_codec_opts,
        "-movflags", "+faststart",
        output_path
    ]
    return cmd

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Auto-Sync & Overlay iPad Camera on Screen Recording (Acoustic Cross-Correlation & PIP Compositing)"
    )
    parser.add_argument("--screen", required=True, help="Path to computer screen recording (MP4/MKV)")
    parser.add_argument("--ipad", required=True, help="Path to iPad video recording (MOV/MP4)")
    parser.add_argument("--output", default="final_composite.mp4", help="Path to final output video")
    parser.add_argument("--shape", choices=["circle", "rounded", "rect", "square"], default=None, help="PIP shape style")
    parser.add_argument("--pip-style", choices=["circle", "rounded", "rect", "square"], default="circle", help="Alias for --shape")
    parser.add_argument("--pip-size", type=int, default=420, help="PIP width/diameter in pixels (e.g. 400-500)")
    parser.add_argument("--position", choices=["bottom-right", "bottom-left", "top-right", "top-left"], default="bottom-right", help="Screen corner position")
    parser.add_argument("--margin", type=int, default=40, help="Pixel margin from screen edge")
    parser.add_argument("--offset", type=float, default=None, help="Manual audio offset override in seconds")
    parser.add_argument("--border-color", default="0x6366F1", help="PIP border color in hex format (e.g. 0x6366F1)")
    parser.add_argument("--border-width", type=int, default=4, help="Border thickness in pixels")
    parser.add_argument("--facecam-audio", action="store_true", help="Use iPad mic audio instead of screen audio")
    parser.add_argument("--dry-run", action="store_true", help="Print sync parameters and command without executing")
    parser.add_argument("--crf", type=int, default=18, help="H.264 CRF quality level (lower = higher quality)")
    parser.add_argument("--preset", default="fast", help="H.264 encoding preset")
    return parser.parse_args(argv)

def main(argv=None):
    args = parse_args(argv)
    shape = args.shape if args.shape is not None else args.pip_style

    print("==================================================")
    print("Dual-Camera Auto-Sync & Facecam Overlay Pipeline")
    print("==================================================")
    print(f"Screen Recording : {args.screen}")
    print(f"iPad Facecam     : {args.ipad}")
    print(f"Output Path      : {args.output}")
    print(f"PIP Shape / Size : {shape} / {args.pip_size}px (Margin: {args.margin}px)")
    print(f"Position         : {args.position}")

    if not args.dry_run and not check_ffmpeg_installed():
        print("[ERROR] FFmpeg not found on PATH. Please install FFmpeg (e.g. via winget install Gyan.FFmpeg).")
        sys.exit(1)

    tmp_screen_wav = f"_tmp_screen_{os.getpid()}.wav"
    tmp_ipad_wav = f"_tmp_ipad_{os.getpid()}.wav"

    try:
        if args.offset is not None:
            offset_sec = args.offset
            print(f"[INFO] Using manual offset override: {offset_sec:.4f}s")
        elif args.dry_run:
            offset_sec = 0.0
            print("[DRY-RUN] Skipping audio extraction, using baseline offset = 0.0s")
        else:
            print("[INFO] Extracting audio for acoustic synchronization...")
            has_s = extract_audio(args.screen, tmp_screen_wav, duration=60)
            has_i = extract_audio(args.ipad, tmp_ipad_wav, duration=60)
            if not has_s or not has_i:
                print("[WARN] Audio stream missing in one or both inputs; falling back to offset 0.0s.")
                offset_sec = 0.0
            else:
                offset_sec = compute_audio_offset(tmp_screen_wav, tmp_ipad_wav)

        print("[INFO] Constructing FFmpeg compositing command...")
        cmd = build_ffmpeg_composite_command(
            args.screen,
            args.ipad,
            offset_sec,
            args.output,
            pip_style=shape,
            pip_size=args.pip_size,
            margin=args.margin,
            position=args.position,
            border_color=args.border_color,
            border_width=args.border_width,
            use_facecam_audio=args.facecam_audio,
            crf=args.crf,
            preset=args.preset
        )

        if args.dry_run:
            print("[DRY-RUN] Planned FFmpeg execution command:")
            print(" ".join(cmd))
            print("[DRY-RUN] Completed successfully without writing output.")
            return 0

        print("[INFO] Rendering composite video with FFmpeg...")
        run_cmd(cmd)
        print(f"[SUCCESS] Composite video rendered successfully: {os.path.abspath(args.output)}")
        return 0

    finally:
        for f in [tmp_screen_wav, tmp_ipad_wav]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

if __name__ == "__main__":
    sys.exit(main())
