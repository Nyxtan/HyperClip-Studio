/**
 * NyxClip Studio - Offline Audio RMS & Highlight Detector
 * Analyzes audio energy offline in the user's browser using WebAudio API (OfflineAudioContext).
 * Identifies the top hype/viral moments using RMS (Root Mean Square) energy + MAD (Median Absolute Deviation).
 * Zero server compute, zero API keys required.
 */

export class HighlightDetector {
  /**
   * Extract audio channel and calculate RMS energy windows.
   * @param {File|Blob} videoBlob
   * @param {Object} options
   * @returns {Promise<Array<{start: number, end: number, score: number, label: string}>>}
   */
  static async detectHighlights(videoBlob, options = {}) {
    const {
      clipMinSeconds = 15,
      clipMaxSeconds = 60,
      windowSizeSec = 1.0,
      topCount = 10
    } = options;

    const arrayBuffer = await videoBlob.arrayBuffer();
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    
    let audioBuffer;
    try {
      audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
    } catch (e) {
      console.warn('[HighlightDetector] Could not decode full audio, falling back to basic split', e);
      return this.generateDefaultHighlights(audioBuffer ? audioBuffer.duration : 60, clipMaxSeconds);
    } finally {
      if (audioContext.state !== 'closed') {
        await audioContext.close();
      }
    }

    const duration = audioBuffer.duration;
    const sampleRate = audioBuffer.sampleRate;
    const rawData = audioBuffer.getChannelData(0); // primary channel
    
    const windowSize = Math.floor(sampleRate * windowSizeSec);
    const numWindows = Math.floor(rawData.length / windowSize);
    const rmsSeries = new Float32Array(numWindows);

    // 1. Calculate RMS energy for each window
    for (let i = 0; i < numWindows; i++) {
      let sumSq = 0;
      const start = i * windowSize;
      const end = start + windowSize;
      for (let j = start; j < end; j++) {
        sumSq += rawData[j] * rawData[j];
      }
      rmsSeries[i] = Math.sqrt(sumSq / windowSize);
    }

    // 2. Compute median and MAD (Median Absolute Deviation)
    const sortedRms = Float32Array.from(rmsSeries).sort();
    const median = sortedRms[Math.floor(sortedRms.length / 2)] || 0.001;
    
    const deviations = new Float32Array(sortedRms.length);
    for (let i = 0; i < sortedRms.length; i++) {
      deviations[i] = Math.abs(sortedRms[i] - median);
    }
    deviations.sort();
    const mad = deviations[Math.floor(deviations.length / 2)] || 0.001;

    // 3. Score windows: Z-score relative to MAD
    const scoredWindows = [];
    for (let i = 0; i < numWindows; i++) {
      const timeSec = i * windowSizeSec;
      const zScore = (rmsSeries[i] - median) / (1.4826 * mad);
      if (zScore > 1.2) { // Hype spike threshold
        scoredWindows.push({ timeSec, zScore });
      }
    }

    // 4. Cluster nearby spikes into clips of [clipMinSeconds, clipMaxSeconds]
    const candidates = [];
    let currentCluster = null;

    for (const w of scoredWindows) {
      if (!currentCluster) {
        currentCluster = { start: Math.max(0, w.timeSec - 5), end: w.timeSec + 10, maxScore: w.zScore };
      } else if (w.timeSec - currentCluster.end < 8) {
        currentCluster.end = Math.min(duration, w.timeSec + 10);
        currentCluster.maxScore = Math.max(currentCluster.maxScore, w.zScore);
      } else {
        candidates.push(currentCluster);
        currentCluster = { start: Math.max(0, w.timeSec - 5), end: w.timeSec + 10, maxScore: w.zScore };
      }
    }
    if (currentCluster) candidates.push(currentCluster);

    // 5. Enforce clip duration constraints and rank
    const results = candidates.map((c, idx) => {
      let dur = c.end - c.start;
      if (dur < clipMinSeconds) {
        const diff = clipMinSeconds - dur;
        c.start = Math.max(0, c.start - diff / 2);
        c.end = Math.min(duration, c.end + diff / 2);
        dur = c.end - c.start;
      }
      if (dur > clipMaxSeconds) {
        c.end = c.start + clipMaxSeconds;
      }
      return {
        id: `highlight-${idx + 1}`,
        start: Math.round(c.start * 10) / 10,
        end: Math.round(c.end * 10) / 10,
        duration: Math.round((c.end - c.start) * 10) / 10,
        score: Math.min(99, Math.round(75 + c.maxScore * 4)),
        label: `Moment #${idx + 1} (Score: ${Math.min(99, Math.round(75 + c.maxScore * 4))})`
      };
    });

    // Sort by score descending and take topCount
    results.sort((a, b) => b.score - a.score);
    return results.slice(0, topCount);
  }

  static generateDefaultHighlights(duration, maxClipSec) {
    const clips = [];
    let cur = 0;
    let idx = 1;
    while (cur < duration && clips.length < 5) {
      const end = Math.min(duration, cur + maxClipSec);
      clips.push({
        id: `highlight-${idx}`,
        start: cur,
        end: end,
        duration: end - cur,
        score: 85 - idx * 2,
        label: `Clip #${idx}`
      });
      cur = end;
      idx++;
    }
    return clips;
  }
}
