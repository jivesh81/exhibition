// SafeSight AI — Frontend Voice Alert Service
// Handles browser-side audio playback for voice alerts with queue, autoplay handling, and deduplication.

const VOICE_STORAGE_KEY = 'safesight_voice_enabled';
const PLAYED_ALERTS_KEY = 'safesight_played_alerts';
const MAX_PLAYED_HISTORY = 50;

// Backend origin for resolving relative audio URLs
const BACKEND_ORIGIN = 'http://127.0.0.1:8000';

function resolveAudioUrl(url) {
  if (!url) return url;
  // If already absolute, return as-is
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('blob:')) {
    return url;
  }
  // Resolve relative to backend origin
  return `${BACKEND_ORIGIN}${url.startsWith('/') ? '' : '/'}${url}`;
}

class VoiceAlertService {
  constructor() {
    this.enabled = false;
    this.queue = [];
    this.playing = false;
    this.currentAudio = null;
    this.playedAlerts = new Set();
    this.onStateChange = null;
    this.onPlaybackStart = null;
    this.onPlaybackEnd = null;
    this.onError = null;
    this.audioContext = null;
    this.unlocked = false;
    this.preloadCache = new Map();
    this.useWebAudio = true; // Try Web Audio first, fallback to HTMLAudio

    // Load persisted state
    this._loadState();
  }

  _loadState() {
    try {
      const stored = localStorage.getItem(VOICE_STORAGE_KEY);
      this.enabled = stored === 'true';

      const played = localStorage.getItem(PLAYED_ALERTS_KEY);
      if (played) {
        const parsed = JSON.parse(played);
        this.playedAlerts = new Set(parsed);
      }
    } catch (e) {
      console.warn('[Voice] Failed to load state:', e);
    }
  }

  _saveState() {
    try {
      localStorage.setItem(VOICE_STORAGE_KEY, this.enabled.toString());
      localStorage.setItem(PLAYED_ALERTS_KEY, JSON.stringify([...this.playedAlerts]));
    } catch (e) {
      console.warn('[Voice] Failed to save state:', e);
    }
  }

  _notifyStateChange() {
    if (this.onStateChange) {
      this.onStateChange(this.getStatus());
    }
  }

  // Initialize AudioContext for autoplay policy compliance
  async _ensureAudioContext() {
    if (!this.audioContext) {
      try {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        console.log('[Voice] AudioContext created');
      } catch (err) {
        console.error('[Voice] Failed to create AudioContext:', err);
        this.useWebAudio = false;
        throw err;
      }
    }
    if (this.audioContext.state === 'suspended') {
      try {
        await this.audioContext.resume();
        console.log('[Voice] AudioContext resumed, state:', this.audioContext.state);
      } catch (err) {
        console.error('[Voice] Failed to resume AudioContext:', err);
        this.useWebAudio = false;
        throw err;
      }
    }
    return this.audioContext;
  }

  // Unlock audio by playing a silent sound (required by browser autoplay policy)
  async unlock() {
    if (this.unlocked) return true;

    try {
      await this._ensureAudioContext();

      // Create a short silent buffer
      const buffer = this.audioContext.createBuffer(1, 1, 22050);
      const source = this.audioContext.createBufferSource();
      source.buffer = buffer;
      source.connect(this.audioContext.destination);
      source.start(0);

      // Wait a bit for it to "play"
      await new Promise(resolve => setTimeout(resolve, 100));

      this.unlocked = true;
      console.log('[Voice] Audio context unlocked successfully');
      return true;
    } catch (err) {
      console.error('[Voice] Failed to unlock audio:', err);
      return false;
    }
  }

  // Preload audio file for faster playback - returns both AudioBuffer (Web Audio) and ArrayBuffer (blob fallback)
  async _preloadAudio(url) {
    const resolvedUrl = resolveAudioUrl(url);
    console.log('[Voice] Preloading audio from:', resolvedUrl);
    
    if (this.preloadCache.has(resolvedUrl)) {
      console.log('[Voice] Using cached audio data');
      return this.preloadCache.get(resolvedUrl);
    }

    try {
      const response = await fetch(resolvedUrl);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const arrayBuffer = await response.arrayBuffer();
      console.log('[Voice] Audio fetched, size:', arrayBuffer.byteLength, 'bytes');
      
      let audioBuffer = null;
      if (this.useWebAudio) {
        try {
          audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer.slice(0));
          console.log('[Voice] Audio decoded successfully, duration:', audioBuffer.duration.toFixed(2), 's, sampleRate:', audioBuffer.sampleRate, 'channels:', audioBuffer.numberOfChannels);
        } catch (decodeErr) {
          console.warn('[Voice] Audio decode failed, will use blob fallback:', decodeErr);
          this.useWebAudio = false;
        }
      }
      
      // Store both ArrayBuffer (for blob fallback) and AudioBuffer (Web Audio)
      const cacheEntry = { arrayBuffer, audioBuffer };
      this.preloadCache.set(resolvedUrl, cacheEntry);
      return cacheEntry;
    } catch (err) {
      console.warn('[Voice] Preload failed for', resolvedUrl, err);
      return null;
    }
  }

  // Enable/disable voice alerts (handles browser autoplay policy)
  async setEnabled(enabled) {
    this.enabled = enabled;
    this._saveState();
    this._notifyStateChange();

    if (enabled) {
      // Unlock audio context on first enable
      const unlocked = await this.unlock();
      console.log('[Voice] setEnabled(true), unlocked:', unlocked);
      if (this.queue.length > 0) {
        this._processQueue();
      }
    }
  }

  // Get current status for UI
  getStatus() {
    return {
      enabled: this.enabled,
      queueLength: this.queue.length,
      isPlaying: this.playing,
      unlocked: this.unlocked,
      currentAlert: this.currentAudio ? {
        worker_id: this.currentAudio.worker_id,
        message: this.currentAudio.message,
        severity: this.currentAudio.severity,
      } : null,
    };
  }

  // Set callbacks
  setCallbacks({ onStateChange, onPlaybackStart, onPlaybackEnd, onError }) {
    this.onStateChange = onStateChange;
    this.onPlaybackStart = onPlaybackStart;
    this.onPlaybackEnd = onPlaybackEnd;
    this.onError = onError;

    // Return unsubscribe function for cleanup
    return () => {
      this.onStateChange = null;
      this.onPlaybackStart = null;
      this.onPlaybackEnd = null;
      this.onError = null;
    };
  }

  // Add alert to queue
  addAlert(alert) {
    // Deduplication: check if we've already played this alert_id
    if (alert.alert_id && this.playedAlerts.has(alert.alert_id)) {
      console.log('[Voice] Duplicate alert suppressed:', alert.alert_id);
      return false;
    }

    // Add to played history
    if (alert.alert_id) {
      this.playedAlerts.add(alert.alert_id);
      if (this.playedAlerts.size > MAX_PLAYED_HISTORY) {
        // Remove oldest entries
        const entries = [...this.playedAlerts];
        this.playedAlerts = new Set(entries.slice(-MAX_PLAYED_HISTORY));
      }
      this._saveState();
    }

    // Priority: CRITICAL=0, HIGH=1, WARNING=2, INFO=3
    const priorityMap = { CRITICAL: 0, HIGH: 1, WARNING: 2, INFO: 3, SAFE: 3 };
    const priority = priorityMap[alert.severity] ?? 3;

    // Insert based on priority (lower number = higher priority)
    const insertIndex = this.queue.findIndex(a => (priorityMap[a.severity] ?? 3) > priority);
    if (insertIndex === -1) {
      this.queue.push(alert);
    } else {
      this.queue.splice(insertIndex, 0, alert);
    }

    console.log('[Voice] Alert queued:', alert.worker_id, alert.severity, 'Queue length:', this.queue.length);
    console.log('[AUTO VOICE QUEUED]', alert.audio_url);
    this._notifyStateChange();

    // Preload audio for this alert
    if (alert.audio_url) {
      const resolvedUrl = resolveAudioUrl(alert.audio_url);
      alert._resolvedAudioUrl = resolvedUrl;
      this._preloadAudio(resolvedUrl).catch(() => {});
    }

    if (this.enabled && !this.playing) {
      this._processQueue();
    }

    return true;
  }

  // Process the queue
  async _processQueue() {
    if (!this.enabled || this.playing || this.queue.length === 0) {
      return;
    }

    this.playing = true;
    this._notifyStateChange();

    while (this.queue.length > 0 && this.enabled) {
      const alert = this.queue.shift();
      this.currentAudio = alert;
      this._notifyStateChange();

      if (this.onPlaybackStart) {
        this.onPlaybackStart(alert);
      }

      try {
        await this._playAlert(alert);
      } catch (error) {
        console.error('[Voice] Playback error:', error);
        if (this.onError) {
          this.onError(alert, error);
        }
      }

      if (this.onPlaybackEnd) {
        this.onPlaybackEnd(alert);
      }

      this.currentAudio = null;
      this._notifyStateChange();

      // Small delay between alerts
      if (this.queue.length > 0) {
        await new Promise(resolve => setTimeout(resolve, 500));
      }
    }

    this.playing = false;
    this._notifyStateChange();
  }

  // Play a single alert using Web Audio API for better control
  async _playAlert(alert) {
    return new Promise(async (resolve, reject) => {
      const audioUrl = alert._resolvedAudioUrl || resolveAudioUrl(alert.audio_url);
      
      if (!audioUrl) {
        console.warn('[Voice] No audio_url for alert:', alert.alert_id);
        resolve();
        return;
      }

      console.log('[Voice] Playing alert:', alert.alert_id, 'url:', audioUrl);
      console.log('[AUTO VOICE PLAYBACK START]', audioUrl);

      // Try Web Audio API first (better for autoplay)
      if (this.useWebAudio) {
        try {
          await this._ensureAudioContext();

          const cacheEntry = await this._preloadAudio(audioUrl);
          const audioBuffer = cacheEntry?.audioBuffer;
          if (audioBuffer && this.audioContext.state === 'running') {
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            const gainNode = this.audioContext.createGain();
            gainNode.gain.value = 0.9;
            source.connect(gainNode);
            gainNode.connect(this.audioContext.destination);

            source.onended = () => {
              console.log('[Voice] Playback finished (Web Audio):', alert.alert_id);
              resolve();
            };

            source.onerror = (err) => {
              console.error('[Voice] Web Audio source error:', err);
              // Fall through to fallback
            };

            source.start(0);
            console.log('[Voice] Started playback via Web Audio API');
            return;
          }
        } catch (webAudioErr) {
          console.warn('[Voice] Web Audio playback failed, falling back to HTMLAudioElement:', webAudioErr);
        }
      }

      // Fallback to HTMLAudioElement using blob URL (avoids CORS issues)
      console.log('[Voice] Falling back to HTMLAudioElement with blob URL');
      
      let arrayBuffer = null;
      const cacheEntry = this.preloadCache.get(audioUrl);
      if (cacheEntry?.arrayBuffer) {
        arrayBuffer = cacheEntry.arrayBuffer;
      } else {
        // Fetch if not cached - with retry for dynamic audio files
        for (let attempt = 1; attempt <= 3; attempt++) {
          try {
            console.log('[Voice] Fetching audio (attempt', attempt, '):', audioUrl);
            const response = await fetch(audioUrl, { 
              credentials: 'omit',
              cache: 'no-cache' 
            });
            if (response.ok) {
              arrayBuffer = await response.arrayBuffer();
              if (arrayBuffer.byteLength > 1000) { // Sanity check: file should be > 1KB
                console.log('[Voice] Audio fetched successfully, size:', arrayBuffer.byteLength);
                break;
              } else {
                console.warn('[Voice] Audio file too small, retrying...');
                arrayBuffer = null;
              }
            } else {
              console.warn('[Voice] Fetch failed with status:', response.status);
            }
          } catch (e) {
            console.warn('[Voice] Fetch attempt', attempt, 'failed:', e.message);
          }
          if (attempt < 3) {
            await new Promise(r => setTimeout(r, 200 * attempt)); // Exponential backoff
          }
        }
      }

      if (!arrayBuffer || arrayBuffer.byteLength < 1000) {
        console.error('[Voice] No valid audio data after retries');
        reject(new Error('No valid audio data'));
        return;
      }

      // Create blob URL (same-origin, avoids CORS)
      const blob = new Blob([arrayBuffer], { type: 'audio/wav' });
      const blobUrl = URL.createObjectURL(blob);
      console.log('[Voice] Created blob URL:', blobUrl);

      const audio = new Audio(blobUrl);
      audio.volume = 1.0; // Full volume
      audio.crossOrigin = 'anonymous'; // Ensure CORS handling
      audio.preload = 'auto';

      let resolved = false;

      const cleanup = () => {
        URL.revokeObjectURL(blobUrl);
      };

      audio.onended = () => {
        if (!resolved) {
          resolved = true;
          cleanup();
          console.log('[Voice] Playback finished (HTMLAudio blob):', alert.alert_id);
          resolve();
        }
      };

      audio.onerror = (e) => {
        if (!resolved) {
          resolved = true;
          cleanup();
          console.error('[Voice] Audio error:', e);
          reject(new Error('Audio playback failed'));
        }
      };

      audio.oncanplaythrough = () => {
        console.log('[Voice] Audio ready to play, duration:', audio.duration);
      };

      // Handle autoplay blocking
      try {
        // Small delay to ensure audio is loaded
        await new Promise(r => setTimeout(r, 50));
        const playPromise = audio.play();
        if (playPromise !== undefined) {
          await playPromise;
          console.log('[Voice] HTMLAudio playback started successfully (blob URL)');
        }
      } catch (err) {
        if (!resolved) {
          if (err.name === 'NotAllowedError') {
            console.warn('[Voice] Autoplay blocked, disabling voice');
            this.enabled = false;
            this._saveState();
            this._notifyStateChange();
            reject(new Error('Autoplay blocked'));
          } else {
            console.error('[Voice] Playback error:', err);
            reject(err);
          }
        }
      }
    });
  }

  // Test voice with a simple message (uses the SAME production pipeline)
  async testVoice(audioUrl) {
    if (!audioUrl) return false;
    console.log('[Voice] Test voice requested with url:', audioUrl);
    await this.unlock();
    return this._playAlert({
      alert_id: `test-${Date.now()}`,
      worker_id: 'TEST',
      worker_name: 'Test',
      severity: 'INFO',
      message: 'SafeSight voice alert system is operational.',
      audio_url: audioUrl,
    });
  }

  // Clear queue
  clearQueue() {
    this.queue = [];
    this._notifyStateChange();
  }

  // Reset played alerts history
  clearHistory() {
    this.playedAlerts.clear();
    this._saveState();
  }
}

export const voiceService = new VoiceAlertService();