/**
 * proctoring.js — Anti-malpractice detection module
 *
 * Listens for tab switches, paste events, and mouse-leave events.
 * Fires a 'proctor-event' CustomEvent on document so app.js can show
 * banners without tight coupling. Also does a fire-and-forget POST to
 * the backend to log each violation.
 *
 * Usage:
 *   const p = new ProctoringManager();
 *   p.start(() => currentPhase, () => ({ turn: 3 }));
 *   p.getStats();  // { tabs: 2, pastes: 1, mouse: 0, ... }
 *   p.stop();
 *   p.reset();
 *
 * Exported as: window.ProctoringManager
 */

(function () {
  'use strict';

  class ProctoringManager {
    constructor() {
      this._tabs   = [];
      this._pastes = [];
      this._mouse  = [];

      this._active     = false;
      this._getPhase   = () => 'idle';
      this._getContext = () => ({});

      // Bound listeners (stored so we can remove them later)
      this._onVisibility  = this._handleVisibility.bind(this);
      this._onPaste       = this._handlePaste.bind(this);
      this._onMouseLeave  = this._handleMouseLeave.bind(this);
    }

    /**
     * Attach DOM listeners and begin proctoring.
     * @param {() => string} getPhase   - Returns current app phase ('interview'|'mcq'|'idle')
     * @param {() => object} getContext - Returns extra context to log with each event
     */
    start(getPhase, getContext) {
      if (this._active) return;
      this._active     = true;
      this._getPhase   = getPhase   || (() => 'idle');
      this._getContext = getContext || (() => ({}));

      document.addEventListener('visibilitychange', this._onVisibility);
      document.addEventListener('paste',            this._onPaste);
      document.addEventListener('mouseleave',       this._onMouseLeave);
    }

    /** Remove DOM listeners and stop proctoring. */
    stop() {
      this._active = false;
      document.removeEventListener('visibilitychange', this._onVisibility);
      document.removeEventListener('paste',            this._onPaste);
      document.removeEventListener('mouseleave',       this._onMouseLeave);
    }

    /** Clear all recorded violation counts (call before starting a new session). */
    reset() {
      this._tabs   = [];
      this._pastes = [];
      this._mouse  = [];
    }

    /**
     * Returns snapshot of violation counts.
     * @returns {{ tabs: number, pastes: number, mouse: number,
     *             tabEvents: object[], pasteEvents: object[], mouseEvents: object[] }}
     */
    getStats() {
      return {
        tabs:        this._tabs.length,
        pastes:      this._pastes.length,
        mouse:       this._mouse.length,
        tabEvents:   [...this._tabs],
        pasteEvents: [...this._pastes],
        mouseEvents: [...this._mouse],
      };
    }

    // ---- Private handlers ------------------------------------------------

    _handleVisibility() {
      const phase = this._getPhase();
      if (phase === 'idle' || !document.hidden) return;

      const entry = { phase, context: this._getContext(), t: Date.now() };
      this._tabs.push(entry);
      this._emit('tab_switch', entry);
    }

    _handlePaste(e) {
      const phase = this._getPhase();
      if (phase === 'idle') return;

      const text  = (e.clipboardData || window.clipboardData).getData('text');
      const entry = { phase, context: this._getContext(), len: text.length, t: Date.now() };
      this._pastes.push(entry);
      this._emit('paste', entry);
    }

    _handleMouseLeave(e) {
      const phase = this._getPhase();
      if (phase === 'idle') return;

      const entry = {
        phase,
        context: this._getContext(),
        dir: e.clientY <= 0 ? 'top' : 'side',
        t: Date.now(),
      };
      this._mouse.push(entry);
      this._emit('mouse_leave', entry);
    }

    // ---- Private helpers -------------------------------------------------

    _emit(type, data) {
      // Notify app.js so it can update banners + counters without coupling
      document.dispatchEvent(
        new CustomEvent('proctor-event', { detail: { type, data } })
      );
      // Fire-and-forget to backend (non-blocking; failure is acceptable)
      this._flagToBackend(type, data);
    }

    async _flagToBackend(type, context) {
      // Derive base URL from the global Cfg if available, else default
      const base = (window._AIP_CFG && window._AIP_CFG.apiBase) || 'http://localhost:8000';
      try {
        await fetch(`${base}/api/proctoring/flag`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ type, phase: context.phase, context }),
        });
      } catch (_) {
        // Network failure is non-critical for client-side proctoring
      }
    }
  }

  window.ProctoringManager = ProctoringManager;
})();
