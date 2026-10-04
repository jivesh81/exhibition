// SafeSight AI — Frontend Voice Alert Service
// Handles browser-side audio playback for voice alerts with queue, autoplay handling, and deduplication.

const VOICE_STORAGE_KEY = 'safesight_voice_enabled';
const PLAYED_ALERTS_KEY = 'safesight_played_alerts';
const MAX_PLAYED_HISTORY = 50;

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

  // Enable/disable voice alerts (handles browser autoplay policy)
  setEnabled(enabled) {
    this.enabled = enabled;
    this._saveState();
    this._notifyStateChange();

    if (enabled && this.queue.length > 0) {
      this._processQueue();
    }
  }

  // Get current status for UI
  getStatus() {
    return {
      enabled: this.enabled,
      queueLength: this.queue.length,
      isPlaying: this.playing,
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
    this._notifyStateChange();

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

  // Play a single alert using HTMLAudioElement
  _playAlert(alert) {
    return new Promise((resolve, reject) => {
      if (!alert.audio_url) {
        console.warn('[Voice] No audio_url for alert:', alert.alert_id);
        resolve();
        return;
      }

      const audio = new Audio(alert.audio_url);
      audio.volume = 0.9;

      audio.onended = () => {
        console.log('[Voice] Playback finished:', alert.alert_id);
        resolve();
      };

      audio.onerror = (e) => {
        console.error('[Voice] Audio error:', e);
        reject(new Error('Audio playback failed'));
      };

      // Handle autoplay blocking
      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise.catch(err => {
          if (err.name === 'NotAllowedError') {
            console.warn('[Voice] Autoplay blocked, disabling voice');
            this.enabled = false;
            this._saveState();
            this._notifyStateChange();
            reject(new Error('Autoplay blocked'));
          } else {
            reject(err);
          }
        });
      }
    });
  }

  // Test voice with a simple message
  async testVoice(audioUrl) {
    if (!audioUrl) return false;
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