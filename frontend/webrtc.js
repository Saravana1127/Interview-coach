/**
 * webrtc.js — WebRTC camera/microphone and Web Speech API wrapper
 *
 * Encapsulates all browser media concerns so app.js stays clean.
 *
 * Usage:
 *   const rtc = new WebRTCManager();
 *
 *   // Camera
 *   const ok = await rtc.startCamera(videoElement);
 *   rtc.stopCamera();
 *
 *   // Speech-to-Text
 *   rtc.initSTT(onResult, onEnd);   // returns true if STT is supported
 *   rtc.startListening();
 *   rtc.stopListening();
 *   rtc.isListening;                // boolean getter
 *
 *   // Text-to-Speech
 *   rtc.speak(text, { onStart, onEnd });
 *   rtc.cancelSpeech();
 *
 * Exported as: window.WebRTCManager
 */

(function () {
  'use strict';

  class WebRTCManager {
    constructor() {
      this._stream      = null;
      this._recognition = null;
      this._listening   = false;
    }

    // ---- Camera ----------------------------------------------------------

    /**
     * Request webcam access and bind stream to a <video> element.
     * @param {HTMLVideoElement} videoEl
     * @returns {Promise<boolean>} true if camera started successfully
     */
    async startCamera(videoEl) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: false,
        });
        this._stream      = stream;
        videoEl.srcObject = stream;
        return true;
      } catch (err) {
        console.warn('[WebRTC] Camera access denied:', err.message);
        return false;
      }
    }

    /** Stop all camera tracks and release the stream. */
    stopCamera() {
      if (this._stream) {
        this._stream.getTracks().forEach(t => t.stop());
        this._stream = null;
      }
    }

    // ---- Speech Recognition (STT) ----------------------------------------

    /**
     * Initialise the SpeechRecognition API.
     * @param {(transcript: string) => void} onResult  - Called with interim+final text
     * @param {() => void}                  onEnd      - Called when recognition stops
     * @returns {boolean} true if the browser supports SpeechRecognition
     */
    initSTT(onResult, onEnd) {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) return false;

      this._recognition                = new SR();
      this._recognition.continuous     = true;
      this._recognition.interimResults = true;
      this._recognition.lang           = 'en-US';

      this._recognition.onresult = (e) => {
        let transcript = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
          transcript += e.results[i][0].transcript;
        }
        onResult?.(transcript);
      };

      this._recognition.onerror = (e) => {
        console.warn('[WebRTC] STT error:', e.error);
      };

      this._recognition.onend = () => {
        this._listening = false;
        onEnd?.();
      };

      return true;
    }

    /** Start microphone capture. No-op if already listening or STT not initialised. */
    startListening() {
      if (!this._recognition || this._listening) return;
      try {
        this._recognition.start();
        this._listening = true;
      } catch (_) { /* recognition may already be running */ }
    }

    /** Stop microphone capture. */
    stopListening() {
      if (!this._recognition || !this._listening) return;
      this._recognition.stop();
      this._listening = false;
    }

    /** @returns {boolean} Whether the microphone is currently active. */
    get isListening() {
      return this._listening;
    }

    // ---- Text-to-Speech (TTS) --------------------------------------------

    /**
     * Speak text using the Web Speech Synthesis API.
     * @param {string}   text
     * @param {object}   [callbacks]
     * @param {Function} [callbacks.onStart] - Fired when speech begins
     * @param {Function} [callbacks.onEnd]   - Fired when speech ends or errors
     */
    speak(text, { onStart, onEnd } = {}) {
      const synth = window.speechSynthesis;
      if (!synth || !text) { onEnd?.(); return; }

      synth.cancel();

      const u    = new SpeechSynthesisUtterance(text);
      u.rate     = 1;
      u.pitch    = 1;
      u.lang     = 'en-US';
      u.onstart  = () => onStart?.();
      u.onend    = () => onEnd?.();
      u.onerror  = () => onEnd?.();

      synth.speak(u);
    }

    /** Cancel any ongoing speech synthesis. */
    cancelSpeech() {
      window.speechSynthesis?.cancel();
    }
  }

  window.WebRTCManager = WebRTCManager;
})();
