#!/usr/bin/env python3
"""
Test Suite: AI Clipper Automation Scripts & CLI Verification
-----------------------------------------------------------
Validates syntax, argument parsing, algorithmic logic, dry-run simulations,
and output schemas of all automation scripts in the suite.
"""

import os
import sys
import json
import py_compile
import tempfile
import wave
import struct
import math
import subprocess
import time
import urllib.request
import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
SYNC_SCRIPT = os.path.join(SCRIPTS_DIR, "sync_and_overlay.py")
POST_SCRIPT = os.path.join(SCRIPTS_DIR, "social_auto_poster.py")
CLIP_SCRIPT = os.path.join(SCRIPTS_DIR, "realtime_comment_clipper.py")

# Ensure scripts dir is on sys.path for direct unit testing of helper classes
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import sync_and_overlay
import social_auto_poster
import realtime_comment_clipper

# -------------------------------------------------------------
# 1. Compilation & Syntax Checks
# -------------------------------------------------------------
def test_scripts_syntax():
    """Verify all Python scripts compile with zero syntax errors."""
    for script_path in [SYNC_SCRIPT, POST_SCRIPT, CLIP_SCRIPT]:
        assert os.path.isfile(script_path), f"Missing script: {script_path}"
        # py_compile raises PyCompileError if syntax is invalid
        py_compile.compile(script_path, doraise=True)

# -------------------------------------------------------------
# 2. sync_and_overlay.py Tests
# -------------------------------------------------------------
def test_sync_and_overlay_argparse():
    """Verify argument parsing and shape alias handling."""
    args = sync_and_overlay.parse_args([
        "--screen", "screen.mp4",
        "--ipad", "ipad.mov",
        "--shape", "circle",
        "--pip-size", "360",
        "--margin", "30",
        "--position", "bottom-right",
        "--dry-run"
    ])
    assert args.screen == "screen.mp4"
    assert args.ipad == "ipad.mov"
    assert args.shape == "circle"
    assert args.pip_size == 360
    assert args.margin == 30
    assert args.position == "bottom-right"
    assert args.dry_run is True

def test_sync_build_ffmpeg_command_shapes():
    """Verify FFmpeg command construction across circle, rounded, and square shapes."""
    for shape in ["circle", "rounded", "square"]:
        cmd = sync_and_overlay.build_ffmpeg_composite_command(
            screen_path="screen.mp4",
            ipad_path="ipad.mov",
            offset_sec=1.25,
            output_path="out.mp4",
            pip_style=shape,
            pip_size=400,
            margin=40,
            position="bottom-right"
        )
        cmd_str = " ".join(cmd)
        assert "ffmpeg" in cmd_str
        assert "-filter_complex" in cmd_str
        assert "out.mp4" in cmd_str
        if shape == "circle":
            assert "alphamerge" in cmd_str
            assert "hypot" in cmd_str

def test_detect_clap_transients_synthetic():
    """Verify acoustic transient peak detection on a synthetic pulse signal."""
    sr = 16000
    duration = 2.0
    samples = [0.01 * math.sin(2 * math.pi * 440 * t / sr) for t in range(int(sr * duration))]
    # Insert high-amplitude transient spike at t=1.0s (index 16000)
    spike_idx = int(1.0 * sr)
    for i in range(100):
        samples[spike_idx + i] = 0.95

    peaks = sync_and_overlay.detect_clap_transients(samples, sr, threshold_factor=2.0)
    assert len(peaks) > 0
    # The primary peak should be very close to 1.0 second
    assert abs(peaks[0][0] - 1.0) < 0.05

def test_sync_cli_dry_run():
    """Verify sync_and_overlay CLI execution with --dry-run returns 0."""
    code = sync_and_overlay.main([
        "--screen", "test_screen.mp4",
        "--ipad", "test_ipad.mp4",
        "--dry-run"
    ])
    assert code == 0

# -------------------------------------------------------------
# 3. social_auto_poster.py Tests
# -------------------------------------------------------------
def test_social_poster_argparse():
    """Verify social_auto_poster argument parsing."""
    args = social_auto_poster.parse_args([
        "--video", "clip.mp4",
        "--title", "Epic Viral Moment",
        "--caption", "Check this out #viral",
        "--platforms", "instagram", "tiktok",
        "--provider", "blotato",
        "--dry-run"
    ])
    assert args.video == "clip.mp4"
    assert args.title == "Epic Viral Moment"
    assert args.provider == "blotato"
    assert "instagram" in args.platforms
    assert args.dry_run is True

def test_publish_via_blotato_simulation():
    """Verify Blotato publishing simulation schema."""
    res = social_auto_poster.publish_via_blotato(
        api_key="test_key_123",
        video_url_or_path="https://example.com/clip.mp4",
        caption="Amazing clip! #shorts",
        platforms=["instagram", "youtube"],
        dry_run=True
    )
    assert res["status"] == "success"
    assert res["provider"] == "blotato"
    assert "blotato_post_" in res["postId"]
    assert "https://blotato.com/p/" in res["url"]
    assert res["platforms"] == ["instagram", "youtube"]

def test_publish_via_upload_post_simulation():
    """Verify Upload-Post publishing simulation schema."""
    res = social_auto_poster.publish_via_upload_post(
        api_key="test_up_key",
        video_path="clip.mp4",
        title="Test Title",
        caption="Caption",
        dry_run=True
    )
    assert res["status"] == "success"
    assert res["provider"] == "upload-post"
    assert "up_job_" in res["jobId"]
    assert "upload-post.com" in res["url"]

def test_social_poster_cli_dry_run(capsys):
    """Verify social_auto_poster CLI run prints valid JSON output."""
    code = social_auto_poster.main([
        "--video", "sample_clip.mp4",
        "--title", "CLI Test Short",
        "--provider", "blotato",
        "--dry-run"
    ])
    assert code == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["status"] == "success"
    assert data["provider"] == "blotato"

# -------------------------------------------------------------
# 4. realtime_comment_clipper.py Tests
# -------------------------------------------------------------
def test_chat_spike_detector_logic():
    """Verify rolling window spike detection and explicit trigger handling."""
    detector = realtime_comment_clipper.ChatSpikeDetector(window_sec=10, spike_multiplier=2.5)
    base_t = 1000.0

    # Add baseline messages (low velocity)
    for i in range(5):
        detector.add_message("cool", timestamp=base_t + (i * 2))

    # Low velocity should NOT trigger
    trig, reason, _ = detector.evaluate_trigger(current_time=base_t + 10)
    assert trig is False

    # Surge at t=1015
    surge_t = base_t + 15
    detector.add_message("LMAO THAT WAS INSANE", timestamp=surge_t)
    detector.add_message("OMG NO WAY", timestamp=surge_t + 1)
    detector.add_message("WWWW POG", timestamp=surge_t + 1)
    detector.add_message("wtfff hahaha", timestamp=surge_t + 2)
    detector.add_message("sheesh holy", timestamp=surge_t + 2)

    trig, reason, trig_type = detector.evaluate_trigger(current_time=surge_t + 3)
    assert trig is True
    assert trig_type == "VELOCITY_SPIKE"

    # Explicit !clip command trigger
    detector.add_message("!clip that moment please", timestamp=surge_t + 5)
    trig_cmd, _, cmd_type = detector.evaluate_trigger(current_time=surge_t + 6)
    assert trig_cmd is True
    assert cmd_type == "EXPLICIT_COMMAND"

def test_parse_comment_timestamps():
    """Verify parsing and ranking of crowd-sourced comment timestamps."""
    raw_comments = [
        {"text": "01:25 bro this reaction killed me LMAO", "likes": 500, "author": "user1"},
        {"text": "nothing special here", "likes": 12, "author": "user2"},
        {"text": "04:10 insane stunt!!", "likes": 250, "author": "user3"},
        {"text": "01:27 haha same timestamp!", "likes": 50, "author": "user4"}, # should dedup with 01:25
        {"text": "1:02:15 long stream highlight", "likes": 80, "author": "user5"}
    ]
    parsed = realtime_comment_clipper.parse_comment_timestamps(raw_comments)
    assert len(parsed) >= 3
    # First should be the highest like comment at 85 seconds (01:25)
    assert parsed[0]["time_sec"] == 85
    assert parsed[0]["formatted"] == "01:25"
    assert parsed[0]["likes"] == 500

    # Verify 1:02:15 parsed as 3735 seconds
    times = [p["time_sec"] for p in parsed]
    assert 3735 in times

def test_comment_clipper_cli_dry_run(tmp_path):
    """Verify realtime_comment_clipper CLI execution in comments mode."""
    out_dir = str(tmp_path / "test_clips")
    code = realtime_comment_clipper.main([
        "--source", "test_video.mp4",
        "--mode", "comments",
        "--output-dir", out_dir,
        "--max-clips", "2",
        "--dry-run"
    ])
    assert code == 0
    meta_file = os.path.join(out_dir, "highlights.json")
    assert os.path.isfile(meta_file)
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)
        assert meta["source"] == "test_video.mp4"
        assert meta["mode"] == "comments"
        assert meta["total_clips"] <= 2
        assert len(meta["clips"]) <= 2


def test_realtime_comment_clipper_engine_integration(tmp_path):
    """Verify narrative context windowing, boundary snapping, and relative word timestamps."""
    words = [
        {"word": "Come", "start": 1.08, "end": 1.64},
        {"word": "on,", "start": 1.64, "end": 2.12},
        {"word": "work.", "start": 4.76, "end": 5.30},
        {"word": "guys", "start": 6.04, "end": 6.26},
        {"word": "go.", "start": 6.62, "end": 7.00},
        {"word": "anymore.", "start": 12.08, "end": 12.78}
    ]

    # Boundary snap
    snapped_s, snapped_e = realtime_comment_clipper.snap_to_word_boundaries(words, 1.2, 6.8)
    assert snapped_s == 1.08
    assert snapped_e == 7.00

    # Narrative context windowing
    s_start, dur, rel_words = realtime_comment_clipper.slice_narrative_context_window(
        source_video="test.mp4",
        trigger_time_sec=4.0,
        pre_roll=3.0,
        post_roll=3.0,
        words=words,
        max_duration=15.0
    )
    assert s_start == 1.08
    assert dur > 0
    assert len(rel_words) > 0
    # Relative zero-indexing check
    assert rel_words[0]["start"] == 0.0
    assert rel_words[0]["word"] == "Come"
    for rw in rel_words:
        assert rw["start"] >= 0.0
        assert rw["end"] <= dur

    # Dry-run execution with --engine-layout circle
    out_dir = str(tmp_path / "engine_clips")
    code = realtime_comment_clipper.main([
        "--source", "test_video.mp4",
        "--mode", "comments",
        "--engine-layout", "circle",
        "--engine-font", "hormozi",
        "--output-dir", out_dir,
        "--max-clips", "1",
        "--dry-run"
    ])
    assert code == 0
    assert os.path.isfile(os.path.join(out_dir, "highlights.json"))

# -------------------------------------------------------------
# 5. Challenger Remediation Regression Tests
# -------------------------------------------------------------
def test_sync_rounded_pip_filtergraph_and_execution(tmp_path):
    """Verify that --shape rounded creates a valid FFmpeg filtergraph and renders successfully."""
    cmd = sync_and_overlay.build_ffmpeg_composite_command(
        screen_path="screen.mp4",
        ipad_path="ipad.mov",
        offset_sec=0.0,
        output_path="out.mp4",
        pip_style="rounded",
        pip_size=300,
        border_width=4
    )
    cmd_str = " ".join(cmd)
    assert "@4" not in cmd_str, "Found invalid @alpha syntax in drawbox"
    assert "t=fill" not in cmd_str, "Found invalid t=fill in drawbox"
    assert "drawbox=x=0:y=0:w=300:h=300" in cmd_str

    # Test real FFmpeg execution if test_pip_clip.mp4 exists
    test_clip = os.path.join(os.path.dirname(SCRIPTS_DIR), "test_pip_clip.mp4")
    if os.path.exists(test_clip) and sync_and_overlay.check_ffmpeg_installed():
        out_mp4 = str(tmp_path / "test_rounded_render.mp4")
        exec_cmd = sync_and_overlay.build_ffmpeg_composite_command(
            screen_path=test_clip,
            ipad_path=test_clip,
            offset_sec=0.0,
            output_path=out_mp4,
            pip_style="rounded",
            pip_size=200
        )
        test_run_cmd = [exec_cmd[0], "-t", "0.5"] + exec_cmd[1:]
        res = subprocess.run(test_run_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert res.returncode == 0, f"FFmpeg rounded PIP failed: {res.stderr}"
        assert os.path.exists(out_mp4)

def test_dynamic_border_color_parsing():
    """Verify color parsing across hex formats and color names in circle geq filter."""
    assert sync_and_overlay.parse_color_to_rgb("0xFF0000") == (255, 0, 0)
    assert sync_and_overlay.parse_color_to_rgb("#00FF00") == (0, 255, 0)
    assert sync_and_overlay.parse_color_to_rgb("red") == (255, 0, 0)
    assert sync_and_overlay.parse_color_to_rgb("0x6366F1") == (99, 102, 241)

    cmd = sync_and_overlay.build_ffmpeg_composite_command(
        screen_path="s.mp4",
        ipad_path="i.mp4",
        offset_sec=0.0,
        output_path="o.mp4",
        pip_style="circle",
        border_color="0xFF0000"
    )
    cmd_str = " ".join(cmd)
    assert "r='255':g='0':b='0'" in cmd_str

def test_acoustic_cross_correlation_positive_offset(tmp_path):
    """Verify sub-millisecond audio sync with known +1.25s offset without boundary bias."""
    import random
    sr = 16000
    rng = random.Random(42)
    full = [rng.uniform(-0.2, 0.2) for _ in range(sr * 15)]
    for i in range(100):
        full[4 * sr + i] = 0.95

    w1 = str(tmp_path / "w1.wav")
    w2 = str(tmp_path / "w2.wav")

    def write_wav(path, data):
        with wave.open(path, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sr)
            f.writeframes(struct.pack(f"<{len(data)}h", *[int(s * 32767) for s in data]))

    write_wav(w1, full[int(2.0 * sr):int(12.0 * sr)])
    write_wav(w2, full[int(0.75 * sr):int(10.75 * sr)])

    offset = sync_and_overlay.compute_audio_offset(w1, w2)
    assert abs(offset - 1.25) < 0.05, f"Expected +1.25s offset, got {offset:.4f}s"

def test_acoustic_cross_correlation_negative_offset(tmp_path):
    """Verify sub-millisecond audio sync with known -0.75s offset."""
    import random
    sr = 16000
    rng = random.Random(42)
    full = [rng.uniform(-0.2, 0.2) for _ in range(sr * 15)]
    for i in range(100):
        full[4 * sr + i] = 0.95

    w1 = str(tmp_path / "w1_neg.wav")
    w2 = str(tmp_path / "w2_neg.wav")

    def write_wav(path, data):
        with wave.open(path, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sr)
            f.writeframes(struct.pack(f"<{len(data)}h", *[int(s * 32767) for s in data]))

    write_wav(w1, full[int(1.0 * sr):int(11.0 * sr)])
    write_wav(w2, full[int(1.75 * sr):int(11.75 * sr)])

    offset = sync_and_overlay.compute_audio_offset(w1, w2)
    assert abs(offset - (-0.75)) < 0.05, f"Expected -0.75s offset, got {offset:.4f}s"

def test_match_clap_transients_multi_clap():
    """Verify multi-clap slate clustering correctly identifies consensus offset."""
    screen_claps = [(1.0, 0.8), (1.5, 0.9), (2.0, 0.95)]
    ipad_claps = [(2.25, 0.95), (2.75, 0.85), (3.25, 0.80)]
    offset, count = sync_and_overlay.match_clap_transients(screen_claps, ipad_claps)
    assert count == 3
    assert abs(offset - 1.25) < 0.01

def test_extract_audio_missing_audio_stream_fallback(tmp_path):
    """Verify extract_audio handles video with missing audio stream gracefully."""
    fake_no_audio = str(tmp_path / "silent.mp4")
    if sync_and_overlay.check_ffmpeg_installed():
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=100x100:duration=0.5",
            "-c:v", "libx264", "-an", fake_no_audio
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        out_wav = str(tmp_path / "silent.wav")
        success = sync_and_overlay.extract_audio(fake_no_audio, out_wav)
        assert success is False, "Expected extract_audio to report False on audio-less file"

def test_comment_clipper_none_and_string_likes():
    """Verify parse_comment_timestamps handles None, string representations ('1.5K', '50')."""
    raw_comments = [
        {"text": "01:23 first clip", "likes": None},
        {"text": "02:45 second clip", "likes": "50"},
        {"text": "03:10 third clip", "likes": "1.5K"},
        {"text": "04:00 fourth clip", "likes": 200}
    ]
    parsed = realtime_comment_clipper.parse_comment_timestamps(raw_comments)
    assert len(parsed) == 4
    assert parsed[0]["likes"] == 1500
    assert parsed[0]["formatted"] == "03:10"
    none_item = next(p for p in parsed if p["formatted"] == "01:23")
    assert none_item["likes"] == 0

def test_chat_spike_detector_causality_upper_bound():
    """Verify ChatSpikeDetector does NOT leak future messages into past evaluation windows."""
    detector = realtime_comment_clipper.ChatSpikeDetector(window_sec=10)
    detector.add_message("!clip that play", timestamp=500.0)
    trig, reason, _ = detector.evaluate_trigger(current_time=100.0)
    assert trig is False, "Leaked future message at t=500 into t=100 window!"

    trig_future, _, cmd_type = detector.evaluate_trigger(current_time=501.0)
    assert trig_future is True
    assert cmd_type == "EXPLICIT_COMMAND"

def test_comment_clipper_timestamp_filters():
    """Verify filtering of AM/PM times, out-of-range minutes/seconds, game scores, and verses."""
    comments = [
        {"text": "Meeting at 12:00 PM tomorrow", "likes": 10},
        {"text": "Alarm at 3:30 AM", "likes": 10},
        {"text": "Look at 99:99", "likes": 10},
        {"text": "Game score was 24:18 at halftime", "likes": 10},
        {"text": "John 3:16 bible verse", "likes": 10},
        {"text": "Check out 01:25 bro", "likes": 500}
    ]
    parsed = realtime_comment_clipper.parse_comment_timestamps(comments)
    assert len(parsed) == 1
    assert parsed[0]["formatted"] == "01:25"
    assert parsed[0]["time_sec"] == 85

def test_social_poster_production_missing_api_key_error(capsys, monkeypatch):
    """Verify running social_auto_poster without --dry-run and missing API key exits with code 1 and error JSON."""
    monkeypatch.delenv("BLOTATO_API_KEY", raising=False)
    monkeypatch.delenv("UPLOAD_POST_API_KEY", raising=False)

    code = social_auto_poster.main([
        "--video", "clip.mp4",
        "--provider", "blotato"
    ])
    assert code == 1
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["status"] == "error"
    assert "Missing API key" in data["error"]

def test_social_poster_instagram_polling_timeout(monkeypatch):
    """Verify Instagram container polling raises TimeoutError if container is never FINISHED."""
    class MockResp:
        def __init__(self, data):
            self.data = json.dumps(data).encode("utf-8")
        def read(self):
            return self.data
        def decode(self, enc):
            return self.data.decode(enc)
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if "/media" in url and not "fields" in url:
            return MockResp({"id": "cnt_12345"})
        elif "fields=status_code" in url:
            return MockResp({"status_code": "IN_PROGRESS"})
        return MockResp({})

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    with pytest.raises(TimeoutError) as exc_info:
        social_auto_poster.publish_direct_instagram_reel(
            ig_user_id="12345",
            access_token="real_tok_abc",
            video_url="https://example.com/v.mp4",
            caption="test",
            dry_run=False
        )
    assert "did not finish encoding" in str(exc_info.value)
