import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clip import (
    write_ass,
    build_video_filter, choose_crop_offset, choose_vertical_game_roi, gameplay_crop_offset, reaction_score,
    should_apply_smart_crop,
    source_identity, select_clip_start,
    DEFAULT_MAX_SECONDS, pick_moments, mask_word, ytdlp_cmd,
)


class ClipperReleaseTests(unittest.TestCase):
    def test_fit_layout_keeps_the_full_source_over_a_blurred_background(self):
        graph = build_video_filter('captions.ass', layout='fit')
        self.assertIn('[b]scale=1080:-2[fg]', graph)
        self.assertIn('overlay=(W-w)/2:(H-h)/2', graph)
        self.assertIn('boxblur=30:5', graph)

    def test_fill_layout_covers_the_whole_vertical_frame(self):
        graph = build_video_filter('captions.ass', layout='fill')
        self.assertIn('force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)*0.5000', graph)
        self.assertNotIn('boxblur', graph)

    def test_fill_layout_with_a_gameplay_roi_still_fills_the_screen(self):
        graph = build_video_filter('captions.ass', layout='fill', source_roi=(0, 150, 360, 389))
        self.assertTrue(graph.startswith('[0:v]crop=360:389:0:150,scale=1080:1920:force_original_aspect_ratio=increase'))
        self.assertNotIn('boxblur', graph)

    def test_gameplay_crop_centres_the_over_the_shoulder_player_anchor(self):
        for width, height in ((1920, 1080), (640, 360)):
            offset = gameplay_crop_offset(width, height, player_x=width * 0.38)
            crop_width = height * 9 / 16
            available = width - crop_width
            crop_center = offset * available + crop_width / 2
            self.assertAlmostEqual(crop_center, width * 0.38)

    def test_corner_facecam_outside_the_centre_keeps_the_character_centred(self):
        # A top-right facecam outside the player crop must not slide the crop to the edge.
        self.assertAlmostEqual(choose_crop_offset(1280, 720, [[(1100, 40, 80, 90)] for _ in range(5)]), gameplay_crop_offset(1280, 720, 1280 * 0.38))
        self.assertAlmostEqual(choose_crop_offset(1920, 1080, [[(180, 90, 70, 70)] for _ in range(4)]), gameplay_crop_offset(1920, 1080, 1920 * 0.38))

    def test_in_game_faces_never_move_the_crop(self):
        self.assertEqual(choose_crop_offset(1920, 1080, [[(1450, 300, 320, 420)] for _ in range(5)]), 0.5)
        self.assertEqual(choose_crop_offset(1920, 1080, [[(1670, 430, 90, 95)] for _ in range(5)]), 0.5)
        self.assertEqual(choose_crop_offset(1920, 1080, [[], [], []]), 0.5)

    def test_facecam_overlapping_the_centre_shifts_only_a_little(self):
        offset = choose_crop_offset(1920, 1080, [[(1180, 60, 90, 95)] for _ in range(5)])
        self.assertLess(offset, 0.5)
        self.assertGreater(offset, 0.2)

    def test_portrait_stack_uses_gameplay_below_a_persistent_top_facecam(self):
        samples = [[(140, 30, 70, 60)] for _ in range(5)]
        roi = choose_vertical_game_roi(360, 640, samples, active_bottom=540)
        self.assertIsNotNone(roi)
        x, y, width, height = roi
        self.assertEqual((x, width), (0, 360))
        self.assertGreaterEqual(y, 110)
        self.assertLessEqual(y + height, 540)

    def test_portrait_without_a_persistent_facecam_keeps_the_full_source(self):
        self.assertIsNone(choose_vertical_game_roi(360, 640, [[], [], []], 540))

    def test_uncertain_face_detection_falls_back_to_full_source_framing(self):
        self.assertFalse(should_apply_smart_crop(True, 0.5, None))
        self.assertTrue(should_apply_smart_crop(True, 1.0, None))
        self.assertTrue(should_apply_smart_crop(True, 0.5, (0, 120, 360, 420)))
        self.assertFalse(should_apply_smart_crop(False, 1.0, None))

    def test_generic_filler_words_do_not_count_as_a_strong_reaction(self):
        filler = [(0, 0.2, word) for word in 'oh no no okay here we go'.split()]
        self.assertEqual(reaction_score(filler), 0)

    def test_clear_reaction_phrases_score_above_filler(self):
        strong = [(0, 0.2, word) for word in 'holy shit that was insane'.split()]
        self.assertGreater(reaction_score(strong), 2)

    def test_unknown_creator_does_not_require_a_repository_allowlist(self):
        source = source_identity({'uploader': 'Creator', 'channel_id': 'UC-new'}, test=False)
        self.assertEqual(source['name'], 'Creator')
        self.assertFalse(source['test'])

    def test_live_capture_defaults_to_running_until_stopped(self):
        self.assertEqual(DEFAULT_MAX_SECONDS, 0)

    def test_highlight_starts_before_the_peak_and_stays_inside_the_chunk(self):
        self.assertAlmostEqual(select_clip_start(21.3, 6, 30, 90), 15.3)
        self.assertEqual(select_clip_start(2, 6, 30, 90), 0)
        self.assertEqual(select_clip_start(89, 6, 30, 90), 60)

    def test_each_selected_clip_uses_the_peak_inside_its_own_window(self):
        audio = np.full(90 * 16000, 0.01, dtype=np.float32)
        audio[20 * 16000:22 * 16000] = 0.8
        audio[60 * 16000:62 * 16000] = 0.8
        with patch('clip.load_audio', return_value=audio), patch('clip.whisper_words', return_value=[]):
            chosen, _ = pick_moments('unused.ts', clip_len=30, top=2, min_score=0, lead_in=6)
        starts = [start for _, start in chosen]
        self.assertEqual(len(starts), 2)
        self.assertEqual(len(set(starts)), 2)
        self.assertTrue(any(14 <= start <= 16 for start in starts), starts)
        self.assertTrue(any(54 <= start <= 56 for start in starts), starts)


class CaptionAndDownloaderTests(unittest.TestCase):
    def test_swear_words_are_masked_in_burned_captions(self):
        self.assertEqual(mask_word("shit"), "s***")
        self.assertEqual(mask_word("Fucking"), "F******")
        self.assertEqual(mask_word("Lucia"), "Lucia")
        self.assertEqual(mask_word("class"), "class")

    def test_ytdlp_uses_node_when_deno_is_missing(self):
        with patch("clip.shutil.which", side_effect=lambda name: "C:/node.exe" if name == "node" else None):
            cmd = ytdlp_cmd("-g", "URL")
        self.assertEqual(cmd[-4:], ["--js-runtimes", "node", "-g", "URL"])

    def test_ytdlp_leaves_default_runtime_when_deno_exists(self):
        with patch("clip.shutil.which", return_value="C:/deno.exe"):
            cmd = ytdlp_cmd("-g", "URL")
        self.assertNotIn("--js-runtimes", cmd)

class PopCaptionTests(unittest.TestCase):
    def _events(self, words):
        import tempfile, os
        from clip import WordTimings
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.ass")
            write_ass(path, WordTimings(words, "en", "English"), 0, 30, None, 400)
            with open(path, encoding="utf-8") as f:
                return [l for l in f.read().splitlines() if l.startswith("Dialogue: 0,")]

    @staticmethod
    def _secs(t):
        h, m, s = t.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    def test_words_pop_in_yellow_one_at_a_time_without_karaoke_sweep(self):
        ev = self._events([(1.0, 1.3, "no"), (1.35, 1.6, "way"), (1.65, 2.0, "bro")])
        self.assertEqual(len(ev), 3)
        self.assertNotIn(r"\kf", "".join(ev))
        self.assertIn(r"\c&H00FFFF&", ev[0].split("NO")[0])          # first word yellow when spoken
        self.assertIn(r"\alpha&HFF&", ev[0].split("NO")[1])          # later words hidden until spoken
        self.assertIn(r"\c&HFFFFFF&", ev[2].split("NO")[0])          # earlier words turn white

    def test_caption_events_never_overlap_so_lines_never_stack(self):
        words = [(i * 0.25, i * 0.25 + 0.6, w) for i, w in enumerate(
            "what is happening right now this is insane look at that car go".split())]
        ev = self._events(words)
        spans = [(self._secs(e.split(",")[1]), self._secs(e.split(",")[2])) for e in ev]
        for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0 + 1e-6)

    def test_phrases_stay_short_enough_for_one_line(self):
        ev = self._events([(i * 0.3, i * 0.3 + 0.25, w) for i, w in enumerate("absolutely unbelievable driving skills".split())])
        for e in ev:
            import re
            visible = re.sub(r"\{[^}]*\}", "", e.split(",,", 2)[-1].split(",,")[-1])
            self.assertLessEqual(len(visible), 24)


if __name__ == '__main__':
    unittest.main()


class SpokenLanguageLockTest(unittest.TestCase):
    def test_hindi_stream_locks_after_votes(self):
        import clip
        clip._forced_language = None
        clip._lang_votes = {"hi": 2, "en": 1}
        self.assertEqual(clip.locked_language(), "hi")

    def test_english_stream_stays_auto(self):
        import clip
        clip._forced_language = None
        clip._lang_votes = {"en": 5, "hi": 1}
        self.assertIsNone(clip.locked_language())

    def test_flag_forces(self):
        import clip
        clip._forced_language = "hi"
        self.assertEqual(clip.locked_language(), "hi")
        clip._forced_language = None
        clip._lang_votes = {}


class DynamicBoundaryTests(unittest.TestCase):
    def test_refine_clip_boundaries_finds_natural_sentence_and_pause(self):
        from clip import refine_clip_boundaries
        words = [
            (5.0, 5.4, "Wait"),
            (5.5, 5.9, "look!"),
            (10.0, 10.4, "He"),
            (10.5, 10.9, "is"),
            (11.0, 11.5, "speeding."),
            (14.0, 14.5, "Holy"),
            (14.6, 15.0, "shit!"), # peak reaction at 15.0
            (16.0, 16.5, "That"),
            (16.6, 17.0, "was"),
            (17.1, 17.6, "close."), # conclusion sentence
            (22.0, 22.5, "Anyway"),
            (22.6, 23.0, "guys,")
        ]
        start, end = refine_clip_boundaries(peak_t=15.0, dur=90.0, words=words,
                                           min_duration=5.0, max_duration=30.0,
                                           target_lead=5.0, target_tail=5.0)
        # Should snap start before sentence at 10.0 or 5.0 (natural pause/sentence start)
        self.assertLessEqual(start, 10.2)
        # Should snap end after "close." around 17.6-18.0, not cutting off mid-sentence
        self.assertGreaterEqual(end, 17.5)
        self.assertLessEqual(end - start, 30.0)
        self.assertGreaterEqual(end - start, 5.0)

    def test_refine_clip_boundaries_respects_min_max_duration(self):
        from clip import refine_clip_boundaries
        words = [(i * 0.5, i * 0.5 + 0.4, f"w{i}") for i in range(100)]
        start, end = refine_clip_boundaries(peak_t=25.0, dur=60.0, words=words,
                                           min_duration=15.0, max_duration=45.0)
        duration = end - start
        self.assertGreaterEqual(duration, 15.0)
        self.assertLessEqual(duration, 45.0)

    def test_refine_clip_boundaries_without_words_anchors_around_peak(self):
        from clip import refine_clip_boundaries
        start, end = refine_clip_boundaries(peak_t=20.0, dur=90.0, words=[],
                                           min_duration=15.0, max_duration=40.0,
                                           target_lead=6.0, target_tail=14.0)
        self.assertEqual(start, 14.0)
        self.assertEqual(end, 34.0)
        self.assertEqual(end - start, 20.0)

    def test_moment_subclass_is_backward_compatible_tuple(self):
        from clip import Moment
        m = Moment(score=3.5, start=12.0, duration=24.5, peak=18.0)
        score, start = m
        self.assertEqual(score, 3.5)
        self.assertEqual(start, 12.0)
        self.assertEqual(m.duration, 24.5)
        self.assertEqual(m.peak, 18.0)
        self.assertEqual(m[0], 3.5)
        self.assertEqual(m[1], 12.0)
        self.assertEqual(m[2], 24.5)
        self.assertEqual(m[3], 18.0)
        self.assertEqual(len(m), 2)

    def test_refine_clip_boundaries_near_chunk_end_guarantees_min_duration(self):
        from clip import refine_clip_boundaries
        words = [(97.0, 97.5, "wow"), (98.0, 98.5, "no!")]
        start, end = refine_clip_boundaries(peak_t=98.0, dur=100.0, words=words,
                                           min_duration=15.0, max_duration=60.0)
        self.assertGreaterEqual(end - start, 15.0)
        self.assertLessEqual(end, 100.0)
        self.assertGreaterEqual(start, 0.0)

    def test_extract_narrative_metadata_structures_hook_climax_punchline(self):
        from clip import extract_narrative_metadata
        words = [
            (10.0, 10.4, "Wait"),
            (10.5, 10.9, "look"),
            (11.0, 11.5, "here!"),
            (15.0, 15.5, "Incredible"),
            (15.6, 16.0, "flip!"),
            (24.0, 24.5, "That"),
            (24.6, 25.0, "is"),
            (25.1, 25.6, "insane.")
        ]
        meta = extract_narrative_metadata(start=10.0, end=26.0, peak_t=15.5, words=words)
        self.assertIn("hook", meta)
        self.assertIn("climax", meta)
        self.assertIn("punchline", meta)
        self.assertIn("pacing", meta)
        self.assertEqual(meta["hook"]["text"], "Wait look here!")
        self.assertEqual(meta["climax"]["text"], "Incredible flip!")
        self.assertEqual(meta["punchline"]["text"], "That is insane.")
        self.assertGreater(meta["pacing"]["words_per_second"], 0)
        self.assertGreater(meta["pacing"]["speech_coverage_ratio"], 0)
