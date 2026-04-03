/**
 * idle-tracker.js — Client-side idle tab eviction.
 *
 * Tracks user inactivity via wall-clock timestamps (Date.now()), shows a
 * warning modal before eviction, and navigates to /paused on timeout.
 * Resistant to Chrome's background tab throttling because elapsed time
 * is computed from absolute timestamps, not accumulated setTimeout intervals.
 *
 * Config is read from window.__idleConfig:
 *   { timeoutMs: number, warningMs: number, enabled: boolean }
 *
 * Call initIdleTracker() after setting window.__idleConfig.
 * Call cleanupIdleTracker() to tear down (used by tests).
 */

/* exported initIdleTracker, cleanupIdleTracker */

var _idleState = null;

function initIdleTracker() {
  var config = window.__idleConfig;
  if (!config || config.enabled === false) {
    return;
  }

  var timeoutMs = config.timeoutMs;
  var warningMs = config.warningMs;
  var lastInteractionTime = Date.now();
  var warningModalShown = false;
  var pollIntervalId = null;
  var countdownIntervalId = null;
  var modalEl = null;

  function resetTimer() {
    lastInteractionTime = Date.now();
  }

  function onInteraction() {
    resetTimer();
    if (warningModalShown) {
      hideWarningModal();
    }
  }

  function getElapsed() {
    return Date.now() - lastInteractionTime;
  }

  function navigateToPaused() {
    var returnPath = window.location.pathname + window.location.search;
    var url = '/paused?return=' + encodeURIComponent(returnPath);
    window.location.assign(url);
  }

  function showWarningModal(remainingSeconds) {
    if (modalEl) return;
    warningModalShown = true;

    modalEl = document.createElement('div');
    modalEl.setAttribute('data-testid', 'idle-warning-modal');
    modalEl.style.cssText = 'position:fixed;inset:0;z-index:99999;' +
      'background:rgba(0,0,0,0.5);display:flex;justify-content:center;' +
      'align-items:center;font-family:system-ui,sans-serif;';

    var card = document.createElement('div');
    card.style.cssText = 'background:white;padding:2rem;border-radius:8px;' +
      'text-align:center;max-width:400px;';

    var heading = document.createElement('h2');
    heading.style.cssText = 'margin:0 0 1rem;font-size:1.25rem;';
    heading.textContent = 'Session will pause in ' + remainingSeconds + ' seconds';

    var btn = document.createElement('button');
    btn.setAttribute('data-testid', 'idle-stay-active-btn');
    btn.style.cssText = 'padding:0.75rem 2rem;background:#1976d2;color:white;' +
      'border:none;border-radius:4px;font-size:1rem;cursor:pointer;';
    btn.textContent = 'Stay Active';
    btn.addEventListener('click', function () {
      onInteraction();
    });

    card.appendChild(heading);
    card.appendChild(btn);
    modalEl.appendChild(card);
    document.body.appendChild(modalEl);

    // Inner countdown — updates every second while modal is visible
    countdownIntervalId = setInterval(function () {
      var remaining = Math.ceil((timeoutMs - getElapsed()) / 1000);
      if (remaining <= 0) {
        navigateToPaused();
      } else {
        heading.textContent = 'Session will pause in ' + remaining + ' seconds';
      }
    }, 1000);
  }

  function hideWarningModal() {
    warningModalShown = false;
    if (countdownIntervalId !== null) {
      clearInterval(countdownIntervalId);
      countdownIntervalId = null;
    }
    if (modalEl) {
      modalEl.remove();
      modalEl = null;
    }
  }

  function pollTick() {
    var elapsed = getElapsed();
    if (elapsed >= timeoutMs) {
      navigateToPaused();
      return;
    }
    if (elapsed >= timeoutMs - warningMs && !warningModalShown) {
      var remaining = Math.ceil((timeoutMs - elapsed) / 1000);
      showWarningModal(remaining);
    }
  }

  function onVisibilityChange() {
    if (document.hidden) return;
    var elapsed = getElapsed();
    if (elapsed >= timeoutMs) {
      navigateToPaused();
    } else if (elapsed >= timeoutMs - warningMs) {
      if (!warningModalShown) {
        var remaining = Math.ceil((timeoutMs - elapsed) / 1000);
        showWarningModal(remaining);
      }
    } else {
      // Below warning threshold — focus counts as interaction
      resetTimer();
    }
  }

  // Attach listeners
  document.addEventListener('click', onInteraction, { passive: true });
  document.addEventListener('keypress', onInteraction, { passive: true });
  document.addEventListener('scroll', onInteraction, { passive: true });
  document.addEventListener('visibilitychange', onVisibilityChange);

  // Start polling
  var pollInterval = Math.min(10000, warningMs / 2);
  pollIntervalId = setInterval(pollTick, pollInterval);

  // Store state for cleanup
  _idleState = {
    pollIntervalId: pollIntervalId,
    onInteraction: onInteraction,
    onVisibilityChange: onVisibilityChange,
    hideWarningModal: hideWarningModal,
    getLastInteractionTime: function () { return lastInteractionTime; }
  };
}

function cleanupIdleTracker() {
  if (!_idleState) return;
  clearInterval(_idleState.pollIntervalId);
  _idleState.hideWarningModal();
  document.removeEventListener('click', _idleState.onInteraction);
  document.removeEventListener('keypress', _idleState.onInteraction);
  document.removeEventListener('scroll', _idleState.onInteraction);
  document.removeEventListener('visibilitychange', _idleState.onVisibilityChange);
  _idleState = null;
}
