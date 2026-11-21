"""Find energetic moments in live gameplay and render centered vertical clips.

This command only records/renders. It never uploads or publishes.
"""
import argparse, glob, json, math, os, re, shutil, subprocess, sys, time
from datetime import datetime
import numpy as np
from live_chat import create_live_chat_collector, score_chat_windows, summarize_chat_window

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(HERE, "output")
TEST_OUT = os.path.join(HERE, "test_out")
WORK = os.path.join(HERE, "work")
DEFAULT_MAX_SECONDS = 0
STRONG_REACTIONS = {"wow", "crazy", "insane", "shit", "fuck", "fucking", "damn", "unbelievable",
                    "ridiculous", "nuts", "wild", "sick", "amazing", "brilliant"}
GAME_EVENTS = {"crash", "crashed", "explode", "exploded", "boom", "chase", "chasing", "wreck", "wrecked"}
REACTION_PHRASES = {
    ("oh", "my", "god"): 1.2, ("holy", "shit"): 1.5, ("holy", "crap"): 1.2,
    ("no", "way"): 1.4, ("what", "the", "hell"): 1.3, ("are", "you", "kidding"): 1.4,
    ("what", "just", "happened"): 1.0, ("no", "fucking", "way"): 2.0,
}
DEFAULT_MIN_SCORE = 2.5
FACE_MODEL = os.path.join(HERE, "models", "face_detection_yunet_2023mar.onnx")


def ytdlp_cmd(*args):
    """yt-dlp needs a JavaScript runtime for YouTube; it only looks for deno by default, so fall back to node.
    Also use android/web clients to bypass YouTube bot blocks."""
    cmd = [sys.executable, "-m", "yt_dlp", "--extractor-args", "youtube:player_client=android,web"]
    if not shutil.which("deno"):
        for rt in ("node", "bun"):
            if shutil.which(rt):
                cmd += ["--js-runtimes", rt]
                break
    return cmd + list(args)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ---------- source info + permission gate ----------
def stream_info(url):
    r = run(ytdlp_cmd("--dump-single-json", "--no-download", "--no-warnings", url))
    if r.returncode:
        sys.exit("yt-dlp could not read that URL:\n" + r.stderr[-400:])
    return json.loads(r.stdout)


def source_identity(info, test=False):
    name = info.get("uploader") or info.get("channel") or "local source"
    return {
        "name": name,
        "credit": info.get("uploader") or info.get("channel") or None,
        "channel_id": info.get("channel_id"),
        "test": bool(test),
    }


# ---------- recording ----------
def start_recorder(url, file_, chunk, max_seconds, outdir, quality="max"):
    os.makedirs(outdir, exist_ok=True)
    pat = os.path.join(outdir, "chunk_%05d.ts")
    if file_:
        inputs = ["-i", file_]
    else:
        # Quality selection: max picks highest resolution available (1080p60/1440p/4k), fallback to 720p if needed
        fmt = "bv+ba/b" if quality == "max" else f"bv[height<={quality}]+ba/b[height<={quality}]/b"
        r = run(ytdlp_cmd("-g", "--no-warnings", "-f", fmt, url))
        lines = [l for l in r.stdout.splitlines() if l.startswith("http")]
        if r.returncode or not lines:
            # Fallback if specific format fails
            r = run(ytdlp_cmd("-g", "--no-warnings", "-f", "bv+ba/b", url))
            lines = [l for l in r.stdout.splitlines() if l.startswith("http")]
        if r.returncode or not lines:
            sys.exit("could not get a stream URL:\n" + r.stderr[-400:])
        inputs = [x for u in lines[:2] for x in ("-i", u)]  # video url (+ separate audio url)
    maps = ["-map", "0:v:0", "-map", "1:a:0"] if len(inputs) == 4 else ["-map", "0:v:0", "-map", "0:a:0?"]
    duration = ["-t", str(max_seconds)] if max_seconds > 0 else []
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, *duration,
           *maps, "-c", "copy", "-f", "segment", "-segment_time", str(chunk),
           "-reset_timestamps", "1", pat]
    return subprocess.Popen(cmd)


# ---------- analysis ----------
_model = None


class WordTimings(list):
    def __init__(self, words=(), spoken_language="unknown", caption_language="English",
                 caption_fallback_reason=None):
        super().__init__(words)
        self.spoken_language = spoken_language or "unknown"
        self.caption_language = caption_language
        self.caption_fallback_reason = caption_fallback_reason


_DEVANAGARI_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l", "क़": "q",
    "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "r", "ढ़": "rh",
    "फ़": "f",
}
_DEVANAGARI_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
}
_DEVANAGARI_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
}
_DEVANAGARI_VIRAMA = "्"

_URDU_CHAR_MAP = {
    "ا": "a", "آ": "aa", "ب": "b", "پ": "p", "ت": "t", "ٹ": "t",
    "ث": "s", "ج": "j", "چ": "ch", "ح": "h", "خ": "kh", "د": "d",
    "ڈ": "d", "ذ": "z", "ر": "r", "ڑ": "r", "ز": "z", "ژ": "zh",
    "س": "s", "ش": "sh", "ص": "s", "ض": "z", "ط": "t", "ظ": "z",
    "ع": "a", "غ": "gh", "ف": "f", "ق": "q", "ک": "k", "گ": "g",
    "ل": "l", "م": "m", "ن": "n", "ں": "n", "و": "o", "ہ": "h",
    "ۂ": "h", "ۃ": "h", "ھ": "h", "ء": "", "ی": "i", "ے": "e",
    "ئ": "e", "ؤ": "o", "ي": "i", "ك": "k", "ى": "y", "ة": "h",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
}

_URDU_COMMON_WORDS = {
    "بھائی": "bhai", "کیا": "kya", "دیکھا": "dekha", "لوسیہ": "lucia",
    "بنگے": "banenge", "مزائے": "maza", "اوپر": "upar", "رہا": "raha",
    "ہے": "hai", "ہیں": "hain", "گا": "ga", "گے": "ge", "گی": "gi",
    "کی": "ki", "کے": "ke", "کا": "ka", "کو": "ko", "سے": "se",
    "میں": "mein", "نہیں": "nahi", "یہ": "ye", "وہ": "woh", "تو": "toh",
    "ہی": "hi", "भी": "bhi", "اب": "ab", "سب": "sab", "گھر": "ghar",
    "گاڑی": "gaadi", "لوگ": "log", "بات": "baat", "کچھ": "kuch",
    "بول": "bol", "چلو": "chalo", "یار": "yaar", "دوست": "dost",
}


def romanize_urdu(text):
    """Transliterate Perso-Arabic/Urdu script output from Whisper into clean Latin Hinglish."""
    clean = re.sub(r"[^\w]", "", text)
    if clean in _URDU_COMMON_WORDS:
        punct = re.sub(r"[\w]", "", text)
        return _URDU_COMMON_WORDS[clean] + punct
    w = text.replace("ائی", "ai").replace("ائے", "aye").replace("او", "o").replace("ای", "i")
    res = []
    for ch in w:
        res.append(_URDU_CHAR_MAP.get(ch, ch))
    return "".join(res)


def romanize_hindi(text):
    """Render Hindi in familiar Latin letters for Hinglish captions."""
    if contains_arabic_script(text):
        return romanize_urdu(text)
    result = []
    index = 0
    while index < len(text):
        char = text[index]
        if char in _DEVANAGARI_CONSONANTS:
            consonant = char
            if index + 1 < len(text) and text[index + 1] == "़" and char + "़" in _DEVANAGARI_CONSONANTS:
                consonant = char + "़"
                index += 1
            result.append(_DEVANAGARI_CONSONANTS[consonant])
            index += 1
            if index < len(text) and text[index] in _DEVANAGARI_MATRAS:
                result.append(_DEVANAGARI_MATRAS[text[index]])
                index += 1
            elif index < len(text) and text[index] == _DEVANAGARI_VIRAMA:
                index += 1
            else:
                result.append("a")
            continue
        if char in _DEVANAGARI_VOWELS:
            result.append(_DEVANAGARI_VOWELS[char])
        elif char in {"ं", "ँ"}:
            result.append("n")
        elif char == "ः":
            result.append("h")
        elif char == "ऽ":
            result.append("'")
        elif char in {"।", "॥"}:
            result.append(". ")
        elif char != _DEVANAGARI_VIRAMA:
            result.append(char)
        index += 1
    return "".join(result)


def contains_arabic_script(text):
    return any("\u0600" <= char <= "\u06ff" or "\u0750" <= char <= "\u077f"
               or "\u08a0" <= char <= "\u08ff" for char in text)


# Language lock. Whisper guesses the language again for every 60 s chunk, and a Hindi streamer's chunk is sometimes
# guessed as English (then the captions come out as English words). So: --spoken-language hi|en forces it, and in
# auto mode the stream's own history decides: after 3 confident chunks, if half or more were Hindi, every later chunk
# is transcribed as Hindi (-> Hinglish captions).
_forced_language = None
_lang_votes = {}
LOCK_MIN_VOTES = 3
LOCK_SHARE = 0.5


def locked_language():
    if _forced_language in ("hi", "en", "ur"):
        return _forced_language
    total = sum(_lang_votes.values())
    if total >= LOCK_MIN_VOTES and (_lang_votes.get("hi", 0) + _lang_votes.get("ur", 0)) / total >= LOCK_SHARE:
        return "hi"
    return None


def whisper_words(audio):
    global _model
    from faster_whisper import WhisperModel
    if _model is None:
        _model = WhisperModel("base", device="cpu", compute_type="int8")
    lock = locked_language()
    segments, info = _model.transcribe(audio, word_timestamps=True, vad_filter=True, task="transcribe", language=lock)
    segments = list(segments)
    spoken_language = info.language or "unknown"
    if lock is None and (getattr(info, "language_probability", 0) or 0) >= 0.6:
        _lang_votes[spoken_language] = _lang_votes.get(spoken_language, 0) + 1
    raw_words = [(w.start, w.end, w.word.strip())
                 for segment in segments for w in (segment.words or [])]
    if spoken_language in ("hi", "ur"):
        words = [(start, end, romanize_hindi(word)) for start, end, word in raw_words]
        return WordTimings(words, spoken_language, "Hinglish")
    if contains_arabic_script(" ".join(word for _, _, word in raw_words)):
        words = [(start, end, romanize_urdu(word)) for start, end, word in raw_words]
        return WordTimings(words, spoken_language, "Hinglish")
    if spoken_language == "en":
        return WordTimings(raw_words, spoken_language, "English")
    reason = "Captions disabled for unsupported or uncertain language"
    return WordTimings(raw_words, spoken_language, "none", reason)


def load_audio(path):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vn", "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def media_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return max(0.0, float(result.stdout.strip()))
    except ValueError:
        return 0.0


def rms_series(x, hop=0.25):
    n = int(16000 * hop)
    k = len(x) // n
    if k == 0:
        return np.zeros(1)
    return 20 * np.log10(np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(1)) + 1e-6)


def reaction_score(words):
    """Score distinct high-energy words and phrases, not repeated filler like 'oh no'."""
    tokens = [re.sub(r"\W", "", word.lower()) for _, _, word in words]
    tokens = [word for word in tokens if word]
    phrase_points = 0.0
    for phrase, weight in REACTION_PHRASES.items():
        size = len(phrase)
        if any(tuple(tokens[index:index + size]) == phrase for index in range(len(tokens) - size + 1)):
            phrase_points += weight
    strong = len(set(tokens) & STRONG_REACTIONS)
    events = len(set(tokens) & GAME_EVENTS)
    return round(min(3.0, phrase_points + min(strong, 3) * 0.45 + min(events, 2) * 0.25), 2)


def select_clip_start(anchor, lead_in, clip_len, duration):
    latest = max(0.0, duration - clip_len)
    return round(min(max(0.0, anchor - lead_in), latest), 2)


class Moment(tuple):
    """
    Moment candidate representation.
    Subclasses tuple so unpacking as (score, start) or indexing as [0], [1], [2] works:
      score, start = moment  (or score, start, *rest = moment)
    While also providing:
      moment.score, moment.start, moment.duration, moment.peak, moment[2]
    """
    def __new__(cls, score, start, duration=30.0, peak=None):
        return super().__new__(cls, (score, start))

    def __init__(self, score, start, duration=30.0, peak=None):
        self.score = score
        self.start = start
        self.duration = duration
        self.peak = peak if peak is not None else round(start + duration / 2, 2)

    def __getitem__(self, index):
        if index == 2:
            return self.duration
        if index == 3:
            return self.peak
        return super().__getitem__(index)

    def __repr__(self):
        return f"Moment(score={self.score}, start={self.start}, duration={self.duration}, peak={self.peak})"


def refine_clip_boundaries(peak_t, dur, words, min_duration=15.0, max_duration=60.0,
                           target_lead=12.0, target_tail=10.0):
    """
    Find natural dynamic boundaries (start, end) around peak_t with narrative arc:
    - Context Setup / Curiosity Hook (start): expands 8-15s LEFT of peak to catch the
      origin of the scenario or sentence start rather than starting mid-event.
    - Climax: peak_t (chat explosion / reaction spike)
    - Punchline / Conclusion (end): seeks 8-12s RIGHT of peak for natural sentence conclusion or pause.
    Guarantees:
      - 0.0 <= start < end <= dur
      - duration is clamped within [min(min_duration, dur), min(max_duration, dur)]
    """
    words_list = list(words) if words else []

    # If the overall chunk duration is smaller than min_duration, clamp min_duration to dur
    effective_min_dur = min(min_duration, dur)
    effective_max_dur = min(max_duration, dur)
    if effective_min_dur > effective_max_dur:
        effective_min_dur = effective_max_dur

    # If no words detected, fall back to dynamic audio window anchored around peak
    if not words_list:
        raw_start = max(0.0, peak_t - target_lead)
        raw_end = min(dur, peak_t + target_tail)
        # Expand if shorter than min_duration
        if raw_end - raw_start < effective_min_dur:
            deficit = effective_min_dur - (raw_end - raw_start)
            take_left = min(raw_start, deficit / 2)
            raw_start -= take_left
            raw_end = min(dur, raw_end + (deficit - take_left))
            if raw_end - raw_start < effective_min_dur:
                raw_start = max(0.0, raw_end - effective_min_dur)
        if raw_end - raw_start > effective_max_dur:
            raw_end = min(dur, raw_start + effective_max_dur)
        return round(raw_start, 2), round(raw_end, 2)

    word_starts = [float(w[0]) for w in words_list]
    word_ends = [float(w[1]) for w in words_list]

    # Target ideal boundaries
    ideal_start = max(0.0, peak_t - target_lead)
    ideal_end = min(dur, peak_t + target_tail)

    # 1. Select Start (Hook): look for pause or sentence boundary within [ideal_start - 4.5, ideal_start + 4.5]
    start_candidates = []
    for idx, (ws, we, wt) in enumerate(words_list):
        if abs(ws - ideal_start) <= 4.5 and ws < peak_t:
            score = 0.0
            # Check gap with previous word
            if idx > 0:
                prev_end = words_list[idx - 1][1]
                gap = ws - prev_end
                if gap >= 0.5:
                    score += 3.0  # clean speech pause
                elif gap >= 0.25:
                    score += 1.5
                if re.search(r"[.!?।]$", words_list[idx - 1][2]):
                    score += 3.5  # previous word ends a sentence
            else:
                score += 2.0  # first word in audio
            # Penalty for distance from ideal_start
            score -= abs(ws - ideal_start) * 0.4
            start_candidates.append((score, ws))

    if start_candidates:
        start_candidates.sort(key=lambda c: c[0], reverse=True)
        chosen_start = start_candidates[0][1]
    else:
        # Nearest word start within 3s of ideal_start
        near_starts = [ws for ws in word_starts if abs(ws - ideal_start) <= 3.0 and ws < peak_t]
        if near_starts:
            chosen_start = min(near_starts, key=lambda s: abs(s - ideal_start))
        else:
            chosen_start = ideal_start

    # Pad slightly into preceding pause if possible
    prev_ends = [we for we in word_ends if we <= chosen_start]
    if prev_ends:
        gap = max(0.0, chosen_start - max(prev_ends))
        chosen_start = max(0.0, chosen_start - min(0.35, gap / 2))
    else:
        chosen_start = max(0.0, chosen_start - 0.2)

    # 2. Select End (Resolution/Punchline): look for sentence end or pause after peak_t
    end_candidates = []
    for idx, (ws, we, wt) in enumerate(words_list):
        if we > peak_t and (we - chosen_start) >= effective_min_dur and (we - chosen_start) <= effective_max_dur:
            score = 0.0
            if re.search(r"[.!?।]$", wt):
                score += 4.0  # sentence ending punctuation
            if idx + 1 < len(words_list):
                next_start = words_list[idx + 1][0]
                gap = next_start - we
                if gap >= 0.5:
                    score += 3.0  # natural pause after statement
                elif gap >= 0.25:
                    score += 1.5
            else:
                score += 2.0  # last word in stream
            # Prefer duration close to ideal_end or target_dur
            target_dur = max(effective_min_dur + 5.0, min(effective_max_dur - 5.0, ideal_end - chosen_start))
            cur_dur = we - chosen_start
            score -= abs(cur_dur - target_dur) * 0.15
            end_candidates.append((score, we))

    if end_candidates:
        end_candidates.sort(key=lambda c: c[0], reverse=True)
        chosen_end = end_candidates[0][1]
    else:
        # Find any word end after peak satisfying min_duration
        valid_ends = [we for we in word_ends if we > peak_t and effective_min_dur <= (we - chosen_start) <= effective_max_dur]
        if valid_ends:
            chosen_end = min(valid_ends, key=lambda e: abs(e - ideal_end))
        else:
            chosen_end = min(dur, chosen_start + effective_min_dur)

    # Trail slightly into following silence
    next_starts = [ws for ws in word_starts if ws >= chosen_end]
    if next_starts:
        gap = max(0.0, min(next_starts) - chosen_end)
        chosen_end = min(dur, chosen_end + min(0.45, gap / 2))
    else:
        chosen_end = min(dur, chosen_end + 0.3)

    # Final clamping to bounds and guaranteed min_duration
    if chosen_end > dur:
        chosen_end = dur

    if (chosen_end - chosen_start) < effective_min_dur:
        # If clipping near the end of stream/chunk, shift chosen_start earlier to satisfy effective_min_dur
        deficit = effective_min_dur - (chosen_end - chosen_start)
        chosen_start = max(0.0, chosen_start - deficit)
        if (chosen_end - chosen_start) < effective_min_dur:
            chosen_end = min(dur, chosen_start + effective_min_dur)

    if (chosen_end - chosen_start) > effective_max_dur:
        chosen_end = min(dur, chosen_start + effective_max_dur)

    if chosen_end <= chosen_start:
        chosen_start = max(0.0, min(peak_t - target_lead, dur - effective_min_dur))
        chosen_end = min(dur, chosen_start + effective_min_dur)

    return round(float(chosen_start), 2), round(float(chosen_end), 2)


def extract_narrative_metadata(start, end, peak_t, words):
    """
    Extract narrative structure (hook, climax, punchline/resolution) and word-level timestamps.
    Returns:
      hook: dict with text, start, end
      climax: dict with peak_t, text
      punchline: dict with text, start, end
      pacing: dict with words_per_second, speech_coverage_ratio
    """
    words_list = [w for w in (words or []) if start <= w[0] < end]
    duration = max(0.1, end - start)
    total_speech_time = sum(max(0.0, min(end, w[1]) - max(start, w[0])) for w in words_list)
    wps = round(len(words_list) / duration, 2)
    coverage = round(min(1.0, total_speech_time / duration), 2)

    if not words_list:
        return {
            "hook": {"text": "", "start": start, "end": min(end, round(start + 3.0, 2))},
            "climax": {"peak_t": peak_t, "text": ""},
            "punchline": {"text": "", "start": max(start, round(end - 3.0, 2)), "end": end},
            "pacing": {"words_per_second": 0.0, "speech_coverage_ratio": 0.0}
        }

    # Hook: opening sentence or phrase within first 3.5s (or up to first punctuation / pause)
    hook_words = []
    for idx, w in enumerate(words_list):
        if w[0] > start + 4.0 and hook_words:
            break
        hook_words.append(w)
        if re.search(r"[.!?।]$", w[2]):
            break
        if idx + 1 < len(words_list) and (words_list[idx + 1][0] - w[1]) >= 0.4:
            break
    if not hook_words:
        hook_words = words_list[:min(4, len(words_list))]
    hook_text = " ".join(w[2] for w in hook_words).strip()
    hook_start = round(hook_words[0][0], 2)
    hook_end = round(hook_words[-1][1], 2)

    # Climax: words around peak_t (+/- 2.5s)
    climax_words = [w for w in words_list if abs(w[0] - peak_t) <= 2.5 or abs(w[1] - peak_t) <= 2.5]
    climax_text = " ".join(w[2] for w in climax_words).strip()

    # Punchline / Resolution: final sentence or words in last 5 seconds
    tail_words = [w for w in words_list if w[1] >= end - 5.0]
    if not tail_words:
        tail_words = words_list[-min(5, len(words_list)):]
    punchline_text = " ".join(w[2] for w in tail_words).strip()
    punchline_start = round(tail_words[0][0], 2)
    punchline_end = round(tail_words[-1][1], 2)

    return {
        "hook": {"text": hook_text, "start": hook_start, "end": hook_end},
        "climax": {"peak_t": round(peak_t, 2), "text": climax_text},
        "punchline": {"text": punchline_text, "start": punchline_start, "end": punchline_end},
        "pacing": {"words_per_second": wps, "speech_coverage_ratio": coverage}
    }


def pick_moments(chunk_path, clip_len=30, top=1, min_score=DEFAULT_MIN_SCORE, lead_in=6, chat_messages=None,
                 moment_source="combined", min_clip_len=15.0, max_clip_len=60.0):
    audio = load_audio(chunk_path)
    if len(audio) < 16000:
        return [], []
    db = rms_series(audio)
    words = whisper_words(audio)
    hop = 0.25
    med = np.median(db); mad = np.median(np.abs(db - med)) + 1.0
    spike = (db - med) / mad
    dur = len(db) * hop
    base_window = float(clip_len) if clip_len else 30.0
    if dur < min(base_window, min_clip_len):
        return [], words
    step = 5.0
    starts = np.arange(0, max(0.1, dur - base_window + 0.1), step)
    chat_scores = score_chat_windows(chat_messages or [], starts.tolist(), base_window) if chat_messages else []
    chat_by_start = {round(row["start"], 3): row for row in chat_scores}
    cands = []
    for start in starts:
        a, b = int(start / hop), int(min(len(spike), (start + base_window) / hop))
        if b <= a:
            continue
        seg = np.sort(spike[a:b])
        loud = seg[-max(3, len(seg) // 10):].mean()
        ws = [w for w in words if start <= w[0] < start + base_window]
        density = len(ws) / max(1.0, base_window)
        reaction = reaction_score(ws)
        chat_row = chat_by_start.get(round(float(start), 3))
        # Chat mode ranks by viewer reactions; speech and sound remain for captions and fallback.
        audio_score = 0.45 * loud + 0.2 * min(density, 4.0) + 1.2 * reaction
        if reaction == 0:
            audio_score *= 0.45
        if moment_source == "chat":
            score = 1.5 * chat_row["signal"] if chat_row else 0.0
        elif moment_source == "audio":
            score = audio_score
        else:
            score = audio_score + (0.85 * chat_row["signal"] if chat_row else 0.0)
        cands.append((score, start, chat_row))
    cands.sort(key=lambda item: (item[0], item[1]), reverse=True)
    chosen = []
    for score, start, chat_row in cands:
        if score < min_score or len(chosen) >= top:
            continue
        a, b = int(start / hop), int(min(len(spike), (start + base_window) / hop))
        peak = (a + int(np.argmax(spike[a:b]))) * hop if b > a else start + base_window / 2
        if moment_source == "chat" and chat_row:
            peak = chat_row["peak_t"]
        elif moment_source == "combined" and chat_row and chat_row["signal"] >= 1.2 and chat_row["peak_chatters"] >= 2:
            peak = chat_row["peak_t"]

        # Dynamic narrative boundary selection
        c_start, c_end = refine_clip_boundaries(
            peak_t=peak,
            dur=dur,
            words=words,
            min_duration=min_clip_len,
            max_duration=max_clip_len,
            target_lead=lead_in,
            target_tail=max(8.0, base_window - lead_in)
        )
        c_len = round(c_end - c_start, 2)

        # De-duplicate: avoid keeping clips with significant overlap (> 30% of shorter)
        clash = False
        for prev in chosen:
            p_start, p_len = prev[1], (prev[2] if len(prev) > 2 else base_window)
            p_end = p_start + p_len
            overlap = min(c_end, p_end) - max(c_start, p_start)
            shorter = min(c_len, p_len)
            if overlap > 0 and (overlap / max(1.0, shorter)) > 0.3:
                clash = True
                break
        if clash:
            continue

        chosen.append(Moment(round(float(score), 2), float(c_start), float(c_len), peak=round(float(peak), 2)))
    return chosen, words


# ---------- captions + cut ----------
def ass_time(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def caption_margin_for_video(video_path, crop=False, source_roi=None):
    """Place captions near the lower third of visible gameplay, not the blurred canvas edge."""
    output_width, output_height = 1080, 1920
    if crop and not source_roi:
        panel_height = output_height
    elif source_roi:
        _, _, source_width, source_height = source_roi
        panel_height = min(output_height, output_width * source_height / max(1, source_width))
    else:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
             "-of", "csv=s=x:p=0", video_path], capture_output=True, text=True,
        )
        dimensions = next((re.fullmatch(r"(\d+)x(\d+)", line.strip())
                           for line in probe.stdout.splitlines() if line.strip()), None)
        if dimensions:
            source_width, source_height = (int(value) for value in dimensions.groups())
            panel_height = min(output_height, output_width * source_height / max(1, source_width))
        else:
            panel_height = output_height
    panel_top = max(0, (output_height - panel_height) / 2)
    caption_center = panel_top + panel_height * 0.76
    baseline_offset = 55
    return max(100, min(1100, round(output_height - caption_center - baseline_offset)))


# Burned-in captions: swear and sexual words are masked (F***) so platforms do not cut reach. The audio is unchanged.
MASK_WORDS = {"fuck", "fucking", "fucked", "fucker", "motherfucker", "shit", "shitty", "bullshit", "bitch", "bitches",
              "pussy", "dick", "cock", "cunt", "nigga", "niggas", "nigger", "whore", "slut", "porn", "sex", "sexy",
              "ass", "asshole", "bastard", "boobs", "tits", "chutiya", "madarchod", "bhenchod", "behenchod", "bc", "mc",
              "gandu", "randi", "lund", "bsdk"}


def mask_word(w):
    core = re.sub(r"[^a-z]", "", w.lower())
    if core in MASK_WORDS or any(core.startswith(x) for x in ("fuck", "motherf", "shit", "nigg")):
        return w[:1] + "*" * max(2, len(w) - 1)
    return w


def write_ass(path, words, start, length, credit, caption_margin_v=400):
    """Pop-up captions: a short phrase (max 3 words, one line) sits at ONE fixed spot. Each word pops in when it is
    spoken, in yellow with a small bounce; words already said turn white; words not yet said stay invisible, so the
    line never shifts. Events never overlap in time (overlapping events make libass stack lines on top of each other)."""
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
            f"Style: Word,Arial Black,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,3,2,40,40,{int(caption_margin_v)},1\n"
            "Style: HookHeader,Arial Black,54,&H0000FFFF,&H00000000,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,6,3,8,50,50,60,1\n"
            "Style: Credit,Arial,44,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,1,8,40,40,150,1\n\n"
            "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")
    ev = []
    inside = [w for w in words if start <= w[0] < start + length]
    caption_language = getattr(words, "caption_language", "English")
    if caption_language in {"English", "Hinglish"}:
        groups, group = [], []
        for item in inside:
            s, e, w = item
            clean = mask_word(re.sub(r"[^\w'!?.,-]", "", w)).upper()
            if not clean:
                continue
            if group:
                prev = group[-1]
                phrase_len = sum(len(part[2]) + 1 for part in group) + len(clean)
                if s - prev[1] > 0.6 or len(group) >= 3 or phrase_len > 18 or re.search(r"[.!?]$", prev[2]):
                    groups.append(group)
                    group = []
            group.append((s, e, clean))
        if group:
            groups.append(group)
        # one timeline of (t_on, t_off, phrase, index_of_spoken_word); t_off never passes the next t_on
        steps = []
        for gi, phrase in enumerate(groups):
            phrase_end = phrase[-1][1] + 0.35
            if gi + 1 < len(groups):
                phrase_end = min(phrase_end, groups[gi + 1][0][0])
            for i, (s, e, _) in enumerate(phrase):
                t_off = phrase[i + 1][0] if i + 1 < len(phrase) else phrase_end
                steps.append((s - start, t_off - start, phrase, i))
        for t_on, t_off, phrase, i in steps:
            t_on, t_off = max(0.0, t_on), min(float(length), t_off)
            a_txt, b_txt = ass_time(t_on), ass_time(t_off)
            if b_txt <= a_txt:
                continue
            parts = []
            for j, (_, _, txt) in enumerate(phrase):
                if j < i:
                    parts.append(r"{\alpha&H00&\c&HFFFFFF&\fscx100\fscy100}" + txt)
                elif j == i:
                    parts.append(r"{\alpha&H00&\c&H00FFFF&\fscx118\fscy118\t(0,110,\fscx100\fscy100)}" + txt)
                else:
                    parts.append(r"{\alpha&HFF&\fscx100\fscy100}" + txt)
            chars = sum(len(p[2]) for p in phrase) + len(phrase) - 1
            fs = max(64, min(104, int(1000 / (0.74 * max(1, chars)))))   # big, but always one line on 1080 px
            ev.append(f"Dialogue: 0,{a_txt},{b_txt},Word,,0,0,0,,{{\\fs{fs}}}{' '.join(parts)}")
    if credit:
        ev.append(f"Dialogue: 1,{ass_time(0)},{ass_time(4)},Credit,,0,0,0,,via {credit}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(ev) + "\n")


def gameplay_crop_offset(frame_width, frame_height, player_x=None):
    """Return the crop offset that centres the usual over-the-shoulder GTA player position."""
    if frame_width <= 0 or frame_height <= 0:
        return 0.5
    crop_width = frame_height * 9 / 16
    available = frame_width - crop_width
    if available <= 0:
        return 0.5
    if player_x is None:
        player_x = frame_width * 0.38
    x0 = float(player_x) - crop_width / 2
    return min(1.0, max(0.0, x0 / available))


def choose_crop_offset(frame_width, frame_height, face_samples):
    """Centre the 9:16 crop on the usual GTA third-person player anchor.
    Only shift further when a persistent facecam overlay overlaps that gameplay crop.
    Faces in the gameplay (NPCs, cutscenes) never move the crop."""
    if frame_width <= 0 or frame_height <= 0:
        return 0.5
    crop_width = frame_height * 9 / 16
    available = frame_width - crop_width
    if available <= 0:
        return 0.5
    threshold = max(3, math.ceil(len(face_samples) * 0.3))
    small = [b for d in face_samples for b in d
             if len(b) >= 4 and 0 < b[2] < frame_width * 0.12 and 0 < b[3] < frame_height * 0.22]
    if len(small) < threshold:
        return 0.5
    cx = [b[0] + b[2] / 2 for b in small]
    cy = [b[1] + b[3] / 2 for b in small]
    mx, my = float(np.median(cx)), float(np.median(cy))
    stable = all(abs(x - mx) <= frame_width * 0.04 and abs(y - my) <= frame_height * 0.06 for x, y in zip(cx, cy))
    if not stable or frame_height * 0.25 <= my <= frame_height * 0.75:
        return 0.5
    base = gameplay_crop_offset(frame_width, frame_height)
    # the webcam box is roughly 3x the detected face; does it reach into the player-centred crop?
    half_cam = 1.5 * float(np.median([b[2] for b in small]))
    cam_l, cam_r = mx - half_cam, mx + half_cam
    left, right = available * base, available * base + crop_width
    if cam_r <= left or cam_l >= right:
        return base
    player_x = frame_width * 0.38
    x0 = cam_r if mx < player_x else cam_l - crop_width   # slide just clear of the cam
    return min(1.0, max(0.0, x0 / available))


def choose_vertical_game_roi(frame_width, frame_height, face_samples, active_bottom=None):
    """Find gameplay below/above a persistent facecam in stacked portrait streams."""
    if frame_width <= 0 or frame_height <= 0 or frame_width / frame_height > 0.75:
        return None
    top_frames, bottom_frames = [], []
    for detections in face_samples:
        top = [box for box in detections if (box[1] + box[3] / 2) < frame_height * 0.3]
        bottom = [box for box in detections if (box[1] + box[3] / 2) > frame_height * 0.7]
        if top:
            top_frames.append(top)
        if bottom:
            bottom_frames.append(bottom)
    threshold = max(3, math.ceil(len(face_samples) * 0.3))
    if len(top_frames) >= threshold and len(bottom_frames) < threshold:
        face_bottom = max(box[1] + box[3] for sample in top_frames for box in sample)
        y0 = max(int(frame_height * 0.14), int(face_bottom + frame_height * 0.05))
        y1 = active_bottom if active_bottom and active_bottom <= frame_height else frame_height
    elif len(bottom_frames) >= threshold and len(top_frames) < threshold:
        face_top = min(box[1] for sample in bottom_frames for box in sample)
        y0 = 0
        y1 = min(int(frame_height * 0.86), int(face_top - frame_height * 0.05))
    else:
        return None
    if y1 - y0 < frame_height * 0.3:
        return None
    return 0, y0, frame_width, y1 - y0


def should_apply_smart_crop(requested, crop_offset, source_roi):
    """Only crop when facecam evidence supports it; otherwise preserve the full source."""
    return bool(requested and (source_roi is not None or abs(float(crop_offset) - 0.5) > 0.01))


def detect_smart_frame(video_path, start, length, sample_count=9):
    """Detect a persistent facecam and return a safe horizontal offset or gameplay ROI."""
    try:
        import cv2
    except ImportError:
        return 0.5, None

    if not os.path.isfile(FACE_MODEL):
        return 0.5, None
    try:
        detector = cv2.FaceDetectorYN.create(FACE_MODEL, "", (320, 320), 0.8, 0.3, 5000)
    except cv2.error:
        return 0.5, None
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return 0.5, None
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    samples = []
    bottom_black_ratios = []
    try:
        for fraction in np.linspace(0.1, 0.9, sample_count):
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + length * fraction) * 1000)
            ok, frame = cap.read()
            detections = []
            if ok and frame is not None:
                original_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                bottom_black_ratios.append(np.mean(original_gray < 12, axis=1))
                scale = min(320 / frame_width, 320 / frame_height)
                resized = cv2.resize(frame, (round(frame_width * scale), round(frame_height * scale)),
                                     interpolation=cv2.INTER_AREA)
                canvas = np.zeros((320, 320, 3), dtype=np.uint8)
                pad_x = (320 - resized.shape[1]) // 2
                pad_y = (320 - resized.shape[0]) // 2
                canvas[pad_y:pad_y + resized.shape[0], pad_x:pad_x + resized.shape[1]] = resized
                _, faces = detector.detect(canvas)
                factor = 1.0 / scale
                for face in (faces if faces is not None else []):
                    x, y, w, h = face[:4]
                    x, y, w, h = int(x), int(y), int(w), int(h)
                    box = (int((x - pad_x) * factor), int((y - pad_y) * factor), int(w * factor), int(h * factor))
                    box = (max(0, box[0]), max(0, box[1]), min(frame_width, box[0] + box[2]) - max(0, box[0]),
                           min(frame_height, box[1] + box[3]) - max(0, box[1]))
                    if box[2] <= 0 or box[3] <= 0:
                        continue
                    center_x = box[0] + box[2] / 2
                    center_y = box[1] + box[3] / 2
                    if center_x < frame_width * 0.38 or center_x > frame_width * 0.62 or frame_width / frame_height <= 0.75:
                        detections.append(box)
            samples.append(detections)
    finally:
        cap.release()
    active_bottom = frame_height
    if bottom_black_ratios:
        black_ratio = np.mean(np.stack(bottom_black_ratios), axis=0)
        row = frame_height - 1
        while row >= 0 and black_ratio[row] >= 0.98:
            row -= 1
        if frame_height - 1 - row >= frame_height * 0.03:
            active_bottom = row + 1
    roi = choose_vertical_game_roi(frame_width, frame_height, samples, active_bottom)
    # Detect best facecam box for PiP overlay
    face_box = None
    all_boxes = [b for d in samples for b in d if len(b) >= 4]
    
    # Priority: Speed's streamer facecam is located in the left overlay region (x < 420, y between 400 and 750)
    streamer_boxes = [b for b in all_boxes if b[0] < frame_width * 0.28 and b[1] > frame_height * 0.35]
    if streamer_boxes:
        bx = int(np.median([b[0] for b in streamer_boxes]))
        by = int(np.median([b[1] for b in streamer_boxes]))
        bw = int(np.median([b[2] for b in streamer_boxes]))
        bh = int(np.median([b[3] for b in streamer_boxes]))
        pad = int(bw * 0.9)
        fx1 = max(0, bx - pad)
        fy1 = max(0, by - int(pad * 1.2))
        fx2 = min(frame_width, bx + bw + pad)
        fy2 = min(frame_height, by + bh + int(pad * 1.5))
        face_box = (fx1, fy1, fx2 - fx1, fy2 - fy1)
    elif all_boxes:
        # Fallback to general face detection only if in corner regions (facecam zone)
        corner_boxes = [b for b in all_boxes if (b[0] < frame_width * 0.3 or b[0] > frame_width * 0.7)]
        if corner_boxes:
            bx = int(np.median([b[0] for b in corner_boxes]))
            by = int(np.median([b[1] for b in corner_boxes]))
            bw = int(np.median([b[2] for b in corner_boxes]))
            bh = int(np.median([b[3] for b in corner_boxes]))
            pad = int(bw * 0.8)
            fx1 = max(0, bx - pad)
            fy1 = max(0, by - int(pad * 1.0))
            fx2 = min(frame_width, bx + bw + pad)
            fy2 = min(frame_height, by + bh + int(pad * 1.2))
            face_box = (fx1, fy1, fx2 - fx1, fy2 - fy1)
        else:
            # Default to Speed's standard stream overlay zone if in-game faces confused the detector
            face_box = (0, int(frame_height * 0.40), int(frame_width * 0.22), int(frame_height * 0.26))
    else:
        # Static fallback for Speed's stream layout
        face_box = (0, int(frame_height * 0.40), int(frame_width * 0.22), int(frame_height * 0.26))
    return choose_crop_offset(frame_width, frame_height, samples), roi, face_box


def build_video_filter(ass_name, crop=False, crop_offset=0.5, source_roi=None, layout="pip", pan_keys=None, face_box=None):
    """layout "pip": gameplay covers full 9:16 frame with streamer facecam overlaid in top-left corner.
    layout "fill": full 9:16 gameplay crop.
    layout "fit": 16:9 gameplay centered over blurred background."""
    offset = min(1.0, max(0.0, float(crop_offset)))
    if crop and layout != "pip":
        layout = "fill"
    if layout == "pip" and face_box:
        fx, fy, fw, fh = face_box
        pip_w, pip_h = 360, 420
        # If player track expression is available, use it for base gameplay, else offset
        if pan_keys and not source_roi:
            from player_track import crop_x_expr
            base_game = f"setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:'{crop_x_expr(pan_keys)}':(ih-1920)/2"
        else:
            base_game = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)*{offset:.4f}:(ih-1920)/2,setpts=PTS-STARTPTS"
        
        filt = (f"[0:v]split[game][cam];"
                f"[game]{base_game}[base];"
                f"[cam]crop={fw}:{fh}:{fx}:{fy},scale={pip_w}:{pip_h},drawbox=x=0:y=0:w={pip_w}:h={pip_h}:color=white@0.9:t=5[pip];"
                f"[base][pip]overlay=60:90[v_pip];"
                f"[v_pip]ass={ass_name}")
        return filt

    if layout in {"fill", "pip"}:
        pre = ""
        if source_roi:
            x, y, width, height = source_roi
            pre = f"crop={width}:{height}:{x}:{y},"
        if pan_keys and not source_roi:                    # follow the player (player_track.py)
            from player_track import crop_x_expr
            return (f"[0:v]setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,"
                    f"crop=1080:1920:'{crop_x_expr(pan_keys)}':(ih-1920)/2,ass={ass_name}")
        return (f"[0:v]{pre}scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920:(iw-1080)*{offset:.4f}:(ih-1920)/2,"
                f"setpts=PTS-STARTPTS,ass={ass_name}")
    if source_roi:
        x, y, width, height = source_roi
        return (f"[0:v]crop={width}:{height}:{x}:{y},split[a][b];"
                "[a]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,boxblur=30:5[bg];[b]scale=1080:-2[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setpts=PTS-STARTPTS,ass={ass_name}")
    return ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=30:5[bg];[b]scale=1080:-2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setpts=PTS-STARTPTS,ass=" + ass_name)


def cut(chunk_path, words, start, length, out_mp4, credit, crop=False, crop_offset=0.5,
        source_roi=None, caption_margin_v=400, layout="pip", pan_keys=None, face_box=None,
        font="beast", ring_color="auto"):
    out_mp4 = os.path.abspath(out_mp4)
    # If using modern locked presets (circle, split, blur), route directly through unified clipper_engine
    if layout in {"circle", "circle_pip", "split", "blur"}:
        try:
            sys.path.append(os.path.join(HERE, "scripts"))
            from clipper_engine import render_clip
            # Format words list for clipper_engine
            words_data = [{"start": round(w[0] - start, 3), "end": round(w[1] - start, 3), "word": str(w[2])}
                          for w in words if start <= w[0] < start + length]
            # Slice audio-video chunk to exact clip window with frame-accurate seek & PTS alignment
            tmp_slice = os.path.abspath(os.path.join(os.path.dirname(out_mp4), f"tmp_slice_{os.getpid()}.mp4"))
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", os.path.abspath(chunk_path),
                "-ss", f"{start:.2f}", "-t", f"{length:.2f}",
                "-vf", "setpts=PTS-STARTPTS",
                "-af", "asetpts=PTS-STARTPTS",
                "-avoid_negative_ts", "make_zero",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k", tmp_slice
            ], check=True)
            render_clip(
                input_file=tmp_slice,
                layout="circle" if layout in {"circle", "circle_pip"} else layout,
                font=font,
                output=out_mp4,
                gemini=False,
                publish=False,
                words_data=words_data,
                ring_color=ring_color
            )
            if os.path.exists(tmp_slice):
                try: os.remove(tmp_slice)
                except OSError: pass
            return True
        except Exception as e:
            print(f"[Clipper Warning] Unified engine render error: {e}, falling back to legacy pipeline...")
    d = os.path.dirname(out_mp4)
    ass_name = "cap_" + os.path.basename(out_mp4) + ".ass"
    write_ass(os.path.join(d, ass_name), words, start, length, credit, caption_margin_v)
    fg = build_video_filter(ass_name, crop=crop, crop_offset=crop_offset, source_roi=source_roi, layout=layout,
                            pan_keys=pan_keys, face_box=face_box)
    bgm_dir = os.path.join(HERE, "assets", "bgm")
    bgm_files = glob.glob(os.path.join(bgm_dir, "*.mp3")) if os.path.isdir(bgm_dir) else []
    # Pick a different sound style dynamically based on start time / hash so every clip gets a unique track
    bgm_path = bgm_files[int(start * 7) % len(bgm_files)] if bgm_files else None

    if bgm_path and os.path.isfile(bgm_path):
        # Mix subtle background beat at 12% volume (-18dB sweet spot) behind commentary
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-i", os.path.abspath(chunk_path),
                            "-stream_loop", "-1", "-i", bgm_path,
                            "-ss", f"{start:.2f}",
                            "-t", f"{length}",
                            "-filter_complex", f"[0:v]{fg},setpts=PTS-STARTPTS[v]; [1:a]volume=0.12[bgm]; [0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2,asetpts=PTS-STARTPTS[aout]",
                            "-map", "[v]",
                            "-map", "[aout]",
                            "-avoid_negative_ts", "make_zero",
                            "-c:v", "libx264", "-preset", "faster",
                            "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                            os.path.basename(out_mp4)], cwd=d, capture_output=True, text=True)
        if r.returncode:
            # Fallback to standard render if complex filter had syntax mismatch
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                                "-i", os.path.abspath(chunk_path),
                                "-ss", f"{start:.2f}", "-t", f"{length}",
                                "-filter_complex", fg, "-af", "asetpts=PTS-STARTPTS",
                                "-avoid_negative_ts", "make_zero",
                                "-c:v", "libx264", "-preset", "faster",
                                "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                                os.path.basename(out_mp4)], cwd=d, capture_output=True, text=True)
    else:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-i", os.path.abspath(chunk_path),
                            "-ss", f"{start:.2f}", "-t", f"{length}",
                            "-filter_complex", fg, "-af", "asetpts=PTS-STARTPTS",
                            "-avoid_negative_ts", "make_zero",
                            "-c:v", "libx264", "-preset", "faster",
                            "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                            os.path.basename(out_mp4)], cwd=d, capture_output=True, text=True)
    os.remove(os.path.join(d, ass_name))
    if r.returncode:
        print("ffmpeg cut failed:", r.stderr[-300:])
        return False
    return True


# ---------- main loop ----------
def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--test", action="store_true", help="render to test_out instead of output")
    ap.add_argument("--chunk", type=int, default=90)
    ap.add_argument("--max-seconds", type=int, default=DEFAULT_MAX_SECONDS,
                    help="stop after N seconds; 0 keeps recording until Ctrl+C (default: 0)")
    ap.add_argument("--clip-len", type=int, default=30,
                    help="target/base clip length in seconds (default: 30)")
    ap.add_argument("--min-clip-len", type=float, default=15.0,
                    help="minimum clip duration in seconds for dynamic boundaries (default: 15.0)")
    ap.add_argument("--max-clip-len", type=float, default=60.0,
                    help="maximum clip duration in seconds for dynamic boundaries (default: 60.0)")
    ap.add_argument("--fixed-len", action="store_true",
                    help="force exact fixed clip length instead of dynamic narrative boundaries")
    ap.add_argument("--lead-in", type=float, default=6,
                    help="seconds before the detected moment to start each clip")
    ap.add_argument("--top", type=int, default=1, help="clips per chunk")
    ap.add_argument("--gameplay-confirmed", action="store_true",
                    help="confirm you visually checked that the source shows actual GTA gameplay before a live capture")
    ap.add_argument("--layout", choices=("pip", "fill", "fit", "split", "blur", "circle", "circle_pip"), default="circle",
                    help="circle (Sample 4 with dynamic timer ring), split (Sample 1), pip (Sample 2), blur (Sample 3), fill: gameplay centered")
    ap.add_argument("--font", default="beast", choices=("beast", "hormozi", "glow", "neon", "clean", "tiktok"),
                    help="subtitle font preset (default: beast/Komika Axis)")
    ap.add_argument("--ring-color", default="auto", choices=("auto", "font", "streamer", "vibe", "yellow", "green", "cyan", "purple", "white"),
                    help="circular timer ring color mode")
    ap.add_argument("--crop", action="store_true", help="same as --layout fill (kept for old commands)")
    ap.add_argument("--moment-source", choices=("chat", "combined", "audio"), default="chat",
                    help="rank by chat reactions (default), combine chat with audio/speech, or use audio/speech only")
    ap.add_argument("--no-chat", action="store_true", help="disable live chat signals and use audio/speech scoring only")
    ap.add_argument("--spoken-language", choices=("auto", "en", "hi"), default="auto",
                    help="auto (default): detect, and lock to Hindi once the stream is clearly Hindi (Hinglish captions); "
                         "hi / en: force it for the whole stream")
    ap.add_argument("--quality", choices=("max", "1080", "720"), default="max",
                    help="Capture quality: 'max' (best 1080p60/1440p/4K), '1080', or '720'")
    ap.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    ap.add_argument("--keep-minutes", type=int, default=30)
    ap.add_argument("--output-dir", default=None, help="override the output folder")
    a = ap.parse_args()
    global _forced_language
    _forced_language = None if a.spoken_language == "auto" else a.spoken_language
    if not a.url and not a.file:
        sys.exit(__doc__)
    if a.file and not a.test:
        sys.exit("--file is only allowed with --test.")
    if a.file:
        a.file = os.path.abspath(a.file)
        if not os.path.isfile(a.file):
            sys.exit(f"Input file not found: {a.file}")
    if a.max_seconds < 0 or a.chunk < 1 or a.clip_len < 1 or a.top < 1:
        sys.exit("--max-seconds must be 0 or more; --chunk, --clip-len and --top must be positive.")
    if a.min_clip_len <= 0 or a.max_clip_len < a.min_clip_len:
        sys.exit("--min-clip-len must be > 0 and --max-clip-len must be >= --min-clip-len.")
    if a.url and not a.test and not a.gameplay_confirmed:
        sys.exit("Live capture stopped: first inspect the source video and confirm actual GTA gameplay is visible. "
                 "Then rerun with --gameplay-confirmed. A GTA title or facecam alone is not gameplay.")
    if a.no_chat:
        a.moment_source = "audio"

    if a.url:
        info = stream_info(a.url)
        if not info.get("is_live") and not a.test:
            sys.exit("The source is not live. Use --test for a local/non-live test input.")
        who = source_identity(info, a.test)
        title = info.get("title", "")
    else:
        who, title, info = source_identity({"uploader": "local source"}, True), os.path.basename(a.file), {}
    out_dir = os.path.abspath(a.output_dir) if a.output_dir else (TEST_OUT if who["test"] else OUTPUT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    wdir = os.path.join(WORK, datetime.now().strftime("%Y%m%d-%H%M%S"))
    print(f"source: {title!r} by {who['name']}  ->  {out_dir}")
    print(f"moment finder: {a.moment_source} (chat mode falls back to audio/speech when chat is unavailable)")
    chat = None
    chat_source, chat_fallback = "disabled", None
    if a.url and not a.test and a.moment_source != "audio":
        chat, chat_source, chat_fallback = create_live_chat_collector(a.url, info.get("id"))
        if chat:
            chat.start()
        else:
            chat_source = "audio-speech-fallback"
            print(f"live chat unavailable ({chat_fallback}); using audio/speech scoring")
    else:
            chat_fallback = "disabled by test mode or audio-only mode"
    rec = start_recorder(a.url, a.file, a.chunk, a.max_seconds, wdir, quality=a.quality)
    done, n_clips = set(), 0
    try:
        while True:
            chunks = sorted(glob.glob(os.path.join(wdir, "chunk_*.ts")))
            finished = chunks if rec.poll() is not None else chunks[:-1]
            todo = [c for c in finished if c not in done]
            if not todo:
                if rec.poll() is not None:
                    break
                time.sleep(3)
                continue
            c = todo[0]; done.add(c)
            print(f"analysing {os.path.basename(c)} ...")
            chunk_length = media_duration(c)
            chunk_end_epoch = os.path.getmtime(c)
            chunk_start_epoch = chunk_end_epoch - chunk_length
            absolute_chat = chat.messages_between(chunk_start_epoch, chunk_end_epoch) if chat else []
            chunk_chat = [{"t": item["epoch"] - chunk_start_epoch,
                           "user": item["user"], "text": item["text"]} for item in absolute_chat]
            chunk_moment_source = a.moment_source
            if chunk_moment_source in {"chat", "combined"} and not chunk_chat:
                chunk_moment_source = "audio"
                if a.moment_source == "chat" and chat:
                    print("  no live chat messages for this chunk; using audio/speech instead")
            moments, words = pick_moments(c, a.clip_len, a.top, a.min_score, a.lead_in,
                                          chunk_chat, chunk_moment_source,
                                          min_clip_len=a.clip_len if a.fixed_len else a.min_clip_len,
                                          max_clip_len=a.clip_len if a.fixed_len else a.max_clip_len)
            for m_item in moments:
                score, start = m_item[0], m_item[1]
                clip_duration = m_item.duration if hasattr(m_item, "duration") else (m_item[2] if len(m_item) > 2 else a.clip_len)
                clip_peak = getattr(m_item, "peak", round(start + clip_duration / 2, 2))
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                name = f"gta-{stamp}-{n_clips + 1}"
                mp4 = os.path.join(out_dir, name + ".mp4")
                layout = "fill" if a.crop else a.layout
                crop_offset, source_roi, face_box = detect_smart_frame(c, start, clip_duration) if layout in {"fill", "pip"} else (0.5, None, None)
                smart_crop = layout in {"fill", "pip"}
                pan_keys = None
                if smart_crop and source_roi is None:
                    from player_track import track_player
                    pan_keys = track_player(c, start, clip_duration)
                    if pan_keys is None:                  # driving / cutscene: the car sits mid-frame
                        crop_offset = 0.5
                caption_margin_v = caption_margin_for_video(c, crop=smart_crop, source_roi=None if smart_crop else source_roi)
                if cut(c, words, start, clip_duration, mp4, who.get("credit"), crop=smart_crop,
                       crop_offset=crop_offset, source_roi=source_roi,
                       caption_margin_v=caption_margin_v, layout=layout, pan_keys=pan_keys, face_box=face_box,
                       font=a.font, ring_color=a.ring_color):
                    n_clips += 1
                    text = " ".join(w[2] for w in words if start <= w[0] < start + clip_duration)
                    chat_summary = summarize_chat_window(chunk_chat, start, clip_duration)
                    narrative = extract_narrative_metadata(start, start + clip_duration, clip_peak, words)
                    if chunk_moment_source == "chat":
                        selection_signals = ["live-chat"]
                    elif chunk_moment_source == "combined":
                        selection_signals = ["audio", "speech", "live-chat"]
                    else:
                        selection_signals = ["audio", "speech"]
                    with open(os.path.join(out_dir, name + ".json"), "w", encoding="utf-8") as meta:
                        json.dump({
                            "video": name + ".mp4", "channel": "gta", "source_url": a.url or a.file,
                            "streamer": who["name"], "credit": who.get("credit"), "stream_title": title,
                            "score": score, "start_time": start, "duration": clip_duration,
                            "peak_time": clip_peak,
                            "narrative": narrative,
                            "transcript": text,
                            "spoken_language": getattr(words, "spoken_language", "unknown"),
                            "caption_language": getattr(words, "caption_language", "English"),
                            "caption_fallback_reason": getattr(words, "caption_fallback_reason", None),
                            "caption_position": "lower-third-of-visible-gameplay",
                            "framing": "fill-9x16" if smart_crop else "full-source-blur-fill",
                            "gameplay_confirmed": a.gameplay_confirmed,
                            "moment_source_requested": a.moment_source,
                            "moment_source_used": chunk_moment_source,
                            "selection_signals": selection_signals,
                            "live_chat_source": chat_source,
                            "live_chat_status": chat.status if chat else "unavailable",
                            "chat_fallback_reason": (chat.error if chat and chat.status == "unavailable" else chat_fallback) if not chat or chat.status == "unavailable" else None,
                            "chat_message_count": chat_summary["message_count"],
                            "unique_chatters": chat_summary["unique_chatters"],
                            "reaction_chatters": chat_summary["reaction_chatters"],
                            "crop_offset": crop_offset if smart_crop else None,
                            "player_track": [[round(t, 2), round(x, 3)] for t, x in pan_keys] if pan_keys else None,
                            "source_roi": list(source_roi) if source_roi else None,
                            "title": None, "youtube_description": None,
                            "instagram_caption": None, "hashtags": [], "post_at": None,
                            "approved": False, "posted": {}, "test": who["test"],
                        }, meta, indent=2, ensure_ascii=False)
                    print(f"  clip {name}.mp4  score {score}")
            for old in glob.glob(os.path.join(wdir, "chunk_*.ts")):
                if old in done and time.time() - os.path.getmtime(old) > a.keep_minutes * 60:
                    os.remove(old)
            if chat:
                chat.discard_before(chunk_end_epoch - 5)
    except KeyboardInterrupt:
        print("stopping capture; finishing current work ...")
    finally:
        if chat:
            chat.stop()
        if rec.poll() is None:
            rec.terminate()
            try:
                rec.wait(timeout=10)
            except subprocess.TimeoutExpired:
                rec.kill()
                rec.wait()
        shutil.rmtree(wdir, ignore_errors=True)
    print(f"done. {n_clips} clip(s) in {out_dir}. Nothing posted.")


if __name__ == "__main__":
    main()
