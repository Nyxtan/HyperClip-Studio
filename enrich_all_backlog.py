"""Enrich all unposted clips with Gemini curiosity hooks, questions, and hashtags before upload.
"""
import json
import os
import sys
import time
from pathlib import Path

from enhance_metadata import clip_prompt, call_gemini, extract_json

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY required.")

    output_dir = Path("output")
    clips = sorted(output_dir.glob("gta-*.json"))
    enriched_count = 0

    print(f"Scanning {len(clips)} total clips for missing AI captions/hooks...")
    for c in clips:
        try:
            with c.open("r", encoding="utf-8") as f:
                meta = json.load(f)

            # Check if this clip needs AI enrichment
            needs_enrich = (
                not meta.get("zernio_post_id") and
                (not meta.get("title") or "Highlight #" in meta.get("title", "") or not meta.get("instagram_caption") or "None" in meta.get("instagram_caption", ""))
            )
            if not needs_enrich:
                continue

            prompt = clip_prompt(meta)
            raw = call_gemini(api_key, "gemini-3.5-flash-lite", prompt)
            suggestions = extract_json(raw)

            meta["title"] = suggestions.get("title") or meta.get("title")
            meta["youtube_description"] = suggestions.get("youtube_description") or meta.get("youtube_description")
            meta["instagram_caption"] = suggestions.get("instagram_caption") or meta.get("instagram_caption")
            meta["hook_suggestion"] = suggestions.get("hook")
            meta["curiosity_header"] = suggestions.get("curiosity_header")

            with c.open("w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            enriched_count += 1
            print(f"[{enriched_count}] Enriched {c.name}: {meta['title']}")
            time.sleep(1)
        except Exception as e:
            print(f"Error enriching {c.name}: {e}")

    print(f"\nDone! Enriched {enriched_count} clips with viral captions and curiosity hooks.")

if __name__ == "__main__":
    main()
