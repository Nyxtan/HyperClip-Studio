"""
Generate better title/description/caption/hooks for a GTA-Auto-Clipper clip JSON using a BYOK LLM.
Safe by default: prints suggestions and does NOT modify files unless --apply is given.
No auto-posting. Keys are read from environment variables only (never stored).

Examples:
  python enhance_metadata.py output/gta-CLIP-ID
  python enhance_metadata.py output/gta-CLIP-ID --provider openrouter --model google/gemini-2.0-flash-001 --apply
  python enhance_metadata.py output/gta-CLIP-ID --provider gemini --model gemini-2.0-flash

Env vars (BYOK):
  OPENROUTER_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY / GOOGLE_API_KEY
"""
import argparse, json, os, re, sys
from pathlib import Path

import requests


def load_json(base):
    p = Path(base)
    if p.suffix.lower() == ".json":
        jp = p
    elif p.suffix.lower() == ".mp4":
        jp = p.with_suffix(".json")
    else:
        jp = p.with_suffix(".json")
    if not jp.exists():
        sys.exit(f"Metadata JSON not found: {jp}")
    with open(jp, "r", encoding="utf-8") as f:
        return jp, json.load(f)


def clip_prompt(meta):
    transcript = (meta.get("transcript") or "").strip()
    streamer = meta.get("streamer") or meta.get("credit") or "the streamer"
    title_src = meta.get("stream_title") or ""
    score = meta.get("score")
    lang = meta.get("spoken_language") or meta.get("caption_language") or "unknown"
    narrative = meta.get("narrative") or {}
    hook_data = narrative.get("hook") or {}
    climax_data = narrative.get("climax") or {}
    punchline_data = narrative.get("punchline") or {}

    return f"""You are a master viral YouTube Shorts & Instagram Reels editor.
Create irresistible titles, descriptions, and curiosity hooks that compel viewers to watch till the end.

Return ONLY valid JSON with keys:
- "title": punchy viral hook title (<= 75 chars) creating an immediate curiosity gap without lying.
- "curiosity_header": short on-screen text (3-7 words) to freeze scrolling in the first 2 seconds (e.g. "He didn't realize what he just did...", "Speed's honest reaction to this...").
- "youtube_description": 1-3 short lines building curiosity + 5-8 viral tags (include #Shorts). Credit: {streamer}.
- "instagram_caption": 1-2 engaging lines with a question asking the audience's opinion + hashtags. Credit: {streamer}.
- "hook": the single spoken or narrative line that starts the story.

Narrative Arc Detected:
- Setup/Hook context: {hook_data.get('text', '')}
- Climax/Peak moment: {climax_data.get('text', '')}
- Punchline/Resolution: {punchline_data.get('text', '')}
- Full Transcript: {transcript if transcript else "(audio/action reaction)"}
- Streamer: {streamer}
- Source: {title_src}
- Highlight Virality Score: {score}
"""


def call_openai_compatible(base_url, api_key, model, prompt):
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You output strict JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }
    r = requests.post(url, headers=headers, json=body, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    return data["choices"][0]["message"]["content"]


def call_gemini(api_key, model, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
    }
    r = requests.post(url, json=body, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def extract_json(text):
    text = text.strip()
    # strip fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def main():
    ap = argparse.ArgumentParser(description="BYOK LLM enhancer for clip metadata (dry-run unless --apply).")
    ap.add_argument("base", help="Clip base path, .json, or .mp4")
    ap.add_argument("--provider", choices=["openrouter", "openai", "groq", "gemini"], default=None,
                    help="LLM provider (auto-detected from available env keys if omitted)")
    ap.add_argument("--model", default=None, help="Model name (provider-specific)")
    ap.add_argument("--apply", action="store_true", help="Write suggested fields into the clip JSON")
    args = ap.parse_args()

    jp, meta = load_json(args.base)
    prompt = clip_prompt(meta)

    provider = args.provider
    key = None
    # auto-detect
    candidates = [
        ("openrouter", os.environ.get("OPENROUTER_API_KEY"), args.model or "google/gemini-2.0-flash-001", "https://openrouter.ai/api/v1"),
        ("openai", os.environ.get("OPENAI_API_KEY"), args.model or "gpt-4o-mini", "https://api.openai.com/v1"),
        ("groq", os.environ.get("GROQ_API_KEY"), args.model or "llama-3.1-8b-instant", "https://api.groq.com/openai/v1"),
        ("gemini", os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"), args.model or "gemini-3.5-flash-lite", None),
    ]
    if provider:
        candidates = [c for c in candidates if c[0] == provider]
    picked = None
    for name, k, model, base in candidates:
        if k:
            picked = (name, k, model, base)
            break
    if not picked:
        sys.exit(
            "No BYOK API key found. Set one of: OPENROUTER_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, GEMINI_API_KEY/GOOGLE_API_KEY\n"
            "Tip (PowerShell, current session): $env:OPENROUTER_API_KEY='...'\n"
            "Nothing was changed."
        )
    name, key, model, base_url = picked

    try:
        if name == "gemini":
            text = call_gemini(key, model, prompt)
        else:
            text = call_openai_compatible(base_url, key, model, prompt)
        suggestion = extract_json(text)
    except Exception as e:
        sys.exit(f"Failed to generate suggestions via {name}/{model}: {e}")

    # normalize keys
    out = {
        "title": (suggestion.get("title") or "").strip(),
        "youtube_description": (suggestion.get("youtube_description") or "").strip(),
        "instagram_caption": (suggestion.get("instagram_caption") or "").strip(),
        "hook": (suggestion.get("hook") or "").strip(),
    }
    print(json.dumps({"provider": name, "model": model, "clip": str(jp), "suggestions": out}, indent=2, ensure_ascii=False))

    if args.apply:
        changed = False
        for k in ("title", "youtube_description", "instagram_caption"):
            if out.get(k):
                meta[k] = out[k]
                changed = True
        if out.get("hook"):
            meta["hook_suggestion"] = out["hook"]
            changed = True
        if changed:
            with open(jp, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            print(f"\nApplied suggestions to: {jp} (approved left as {meta.get('approved')!r}; nothing published)")
        else:
            print("\nNo fields to apply.")
    else:
        print("\nDry run: no files changed. Re-run with --apply to write title/description/caption into the JSON.")


if __name__ == "__main__":
    main()
