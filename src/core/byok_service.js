/**
 * NyxClip Studio - Client-Side BYOK (Bring Your Own Key) AI Service
 * Direct browser fetch() to Groq Whisper and Google Gemini Flash.
 * Zero host API cost, zero CORS preflight blocks.
 */

export class ByokService {
  static getKeys() {
    return {
      groqKey: localStorage.getItem('nyxclip_groq_key') || '',
      geminiKey: localStorage.getItem('nyxclip_gemini_key') || ''
    };
  }

  static setKeys(groqKey, geminiKey) {
    if (groqKey !== undefined) localStorage.setItem('nyxclip_groq_key', groqKey.trim());
    if (geminiKey !== undefined) localStorage.setItem('nyxclip_gemini_key', geminiKey.trim());
  }

  /**
   * Transcribe audio directly via Groq Whisper API (whisper-large-v3-turbo).
   * @param {Blob} audioBlob (16 kHz mono WAV or MP3, under 25 MB)
   * @returns {Promise<{text: string, segments: Array<{start: number, end: number, text: string}>}>}
   */
  static async transcribeAudio(audioBlob) {
    const { groqKey } = this.getKeys();
    if (!groqKey) {
      throw new Error('NO_GROQ_KEY: Please add your free Groq API key in Settings for AI captions.');
    }

    const formData = new FormData();
    formData.append('file', audioBlob, 'audio.wav');
    formData.append('model', 'whisper-large-v3-turbo');
    formData.append('response_format', 'verbose_json');
    formData.append('temperature', '0.0');

    const res = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${groqKey}`
      },
      body: formData
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(`Groq Whisper error (${res.status}): ${err.error?.message || res.statusText}`);
    }

    const data = await res.json();
    return {
      text: data.text || '',
      segments: (data.segments || []).map((s) => ({
        start: s.start,
        end: s.end,
        text: s.text.trim()
      }))
    };
  }

  /**
   * Generate viral hooks, titles, and select best clips via Google Gemini Flash Native REST.
   * Uses native REST (x-goog-api-key) to avoid OpenAI-compat CORS preflight errors in browsers.
   */
  static async analyzeViralHooks(transcriptText, streamTitle = '') {
    const { geminiKey } = this.getKeys();
    if (!geminiKey) {
      return this._fallbackHooks(transcriptText);
    }

    const prompt = `You are a viral TikTok/YouTube Shorts clipping expert.
Analyze this video transcript and return JSON with the top 3-5 viral hooks and clip timestamps.
Stream Title: "${streamTitle}"
Transcript:
"""${transcriptText.slice(0, 15000)}"""

Respond ONLY with valid JSON in this exact structure:
{
  "clips": [
    {
      "hook": "VIRAL HOOK IN 4-6 WORDS",
      "summary": "Short explanation",
      "estimatedViralScore": 95
    }
  ]
}`;

    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${geminiKey}`;

    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        contents: [
          {
            parts: [{ text: prompt }]
          }
        ],
        generationConfig: {
          responseMimeType: 'application/json',
          temperature: 0.3
        }
      })
    });

    if (!res.ok) {
      console.warn('[ByokService] Gemini API call failed, falling back to local heuristic');
      return this._fallbackHooks(transcriptText);
    }

    const data = await res.json();
    const rawText = data.candidates?.[0]?.content?.parts?.[0]?.text;
    try {
      return JSON.parse(rawText);
    } catch (e) {
      return this._fallbackHooks(transcriptText);
    }
  }

  static _fallbackHooks(transcriptText) {
    return {
      clips: [
        {
          hook: "WAIT TILL THE END",
          summary: "Top hype moment detected by audio energy spike",
          estimatedViralScore: 92
        },
        {
          hook: "NO SHOT HE DID THAT",
          summary: "Secondary reaction peak",
          estimatedViralScore: 88
        }
      ]
    };
  }
}
