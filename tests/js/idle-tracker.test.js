import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';

describe('idle-tracker.js', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Mock window.location.assign
    delete window.location;
    window.location = {
      pathname: '/annotation/test-uuid',
      search: '',
      assign: vi.fn()
    };
  });

  afterEach(() => {
    cleanupIdleTracker();
    delete window.__idleConfig;
    // Remove any modal DOM left behind
    var modal = document.querySelector('[data-testid="idle-warning-modal"]');
    if (modal) modal.remove();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe('TestIdleTrackerConfig', () => {
    test('AC5.3: no listeners when config absent', () => {
      delete window.__idleConfig;
      var addSpy = vi.spyOn(document, 'addEventListener');
      initIdleTracker();
      expect(addSpy).not.toHaveBeenCalled();
    });

    test('AC5.3: no listeners when enabled is false', () => {
      window.__idleConfig = { timeoutMs: 10000, warningMs: 3000, enabled: false };
      var addSpy = vi.spyOn(document, 'addEventListener');
      initIdleTracker();
      expect(addSpy).not.toHaveBeenCalled();
    });

    test('attaches listeners when enabled', () => {
      window.__idleConfig = { timeoutMs: 10000, warningMs: 3000, enabled: true };
      var addSpy = vi.spyOn(document, 'addEventListener');
      initIdleTracker();
      var eventTypes = addSpy.mock.calls.map(c => c[0]);
      expect(eventTypes).toContain('click');
      expect(eventTypes).toContain('keypress');
      expect(eventTypes).toContain('scroll');
      expect(eventTypes).toContain('visibilitychange');
    });
  });

  describe('TestIdleTrackerTimerReset', () => {
    test('AC1.4: click resets the idle timer', () => {
      window.__idleConfig = { timeoutMs: 30000, warningMs: 5000, enabled: true };
      initIdleTracker();

      // Advance 20 seconds
      vi.advanceTimersByTime(20000);

      // Simulate click — resets timer
      document.dispatchEvent(new Event('click'));

      // Advance another 20 seconds (total 40s, but timer was reset at 20s)
      vi.advanceTimersByTime(20000);

      // Should NOT have navigated (only 20s since reset, timeout is 30s)
      expect(window.location.assign).not.toHaveBeenCalled();
    });

    test('AC1.4: keypress resets the idle timer', () => {
      window.__idleConfig = { timeoutMs: 30000, warningMs: 5000, enabled: true };
      initIdleTracker();

      vi.advanceTimersByTime(20000);
      document.dispatchEvent(new Event('keypress'));
      vi.advanceTimersByTime(20000);

      expect(window.location.assign).not.toHaveBeenCalled();
    });

    test('AC1.4: scroll resets the idle timer', () => {
      window.__idleConfig = { timeoutMs: 30000, warningMs: 5000, enabled: true };
      initIdleTracker();

      vi.advanceTimersByTime(20000);
      document.dispatchEvent(new Event('scroll'));
      vi.advanceTimersByTime(20000);

      expect(window.location.assign).not.toHaveBeenCalled();
    });
  });

  describe('TestIdleTrackerWallClock', () => {
    test('AC1.1/AC1.5: navigates to /paused after timeout', () => {
      window.__idleConfig = { timeoutMs: 10000, warningMs: 3000, enabled: true };
      initIdleTracker();

      // Advance past timeout
      vi.advanceTimersByTime(11000);

      expect(window.location.assign).toHaveBeenCalledWith(
        '/paused?return=%2Fannotation%2Ftest-uuid'
      );
    });

    test('AC1.1: navigation URL includes current path and search', () => {
      window.location.pathname = '/courses/123';
      window.location.search = '?tab=settings';
      window.__idleConfig = { timeoutMs: 5000, warningMs: 2000, enabled: true };
      initIdleTracker();

      vi.advanceTimersByTime(6000);

      expect(window.location.assign).toHaveBeenCalledWith(
        '/paused?return=%2Fcourses%2F123%3Ftab%3Dsettings'
      );
    });
  });

  describe('TestWarningModal', () => {
    test('AC2.1: modal appears at warning threshold with countdown', () => {
      window.__idleConfig = { timeoutMs: 10000, warningMs: 3000, enabled: true };
      initIdleTracker();

      // Advance to warning threshold (10s - 3s = 7s)
      vi.advanceTimersByTime(7500);

      var modal = document.querySelector('[data-testid="idle-warning-modal"]');
      expect(modal).not.toBeNull();
      expect(modal.textContent).toContain('seconds');
    });

    test('AC2.2: Stay Active button dismisses modal and resets timer', () => {
      window.__idleConfig = { timeoutMs: 10000, warningMs: 3000, enabled: true };
      initIdleTracker();

      vi.advanceTimersByTime(7500);
      var btn = document.querySelector('[data-testid="idle-stay-active-btn"]');
      expect(btn).not.toBeNull();

      btn.click();

      var modal = document.querySelector('[data-testid="idle-warning-modal"]');
      expect(modal).toBeNull();

      // Should not navigate even after more time (timer was reset)
      vi.advanceTimersByTime(8000);
      expect(window.location.assign).not.toHaveBeenCalled();
    });

    test('AC2.3: any click during warning dismisses modal', () => {
      window.__idleConfig = { timeoutMs: 10000, warningMs: 3000, enabled: true };
      initIdleTracker();

      vi.advanceTimersByTime(7500);
      expect(document.querySelector('[data-testid="idle-warning-modal"]')).not.toBeNull();

      // Click anywhere on document
      document.dispatchEvent(new Event('click'));

      expect(document.querySelector('[data-testid="idle-warning-modal"]')).toBeNull();
    });
  });

  describe('TestVisibilityChange', () => {
    test('AC2.5: immediate eviction if past timeout on refocus', () => {
      window.__idleConfig = { timeoutMs: 10000, warningMs: 3000, enabled: true };
      initIdleTracker();

      // Advance past timeout without triggering poll (simulate bg tab)
      vi.setSystemTime(Date.now() + 15000);

      // Simulate tab refocus
      Object.defineProperty(document, 'hidden', { value: false, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));

      expect(window.location.assign).toHaveBeenCalledWith(
        '/paused?return=%2Fannotation%2Ftest-uuid'
      );
    });

    test('AC2.4: modal appears on refocus in warning window', () => {
      window.__idleConfig = { timeoutMs: 10000, warningMs: 3000, enabled: true };
      initIdleTracker();

      // Advance into warning window (8s elapsed, 2s remaining)
      vi.setSystemTime(Date.now() + 8000);

      Object.defineProperty(document, 'hidden', { value: false, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));

      var modal = document.querySelector('[data-testid="idle-warning-modal"]');
      expect(modal).not.toBeNull();
      expect(window.location.assign).not.toHaveBeenCalled();
    });

    test('AC2.6: below warning threshold resets timer on refocus', () => {
      window.__idleConfig = { timeoutMs: 10000, warningMs: 3000, enabled: true };
      initIdleTracker();

      // Advance 4s (below 7s warning threshold)
      vi.setSystemTime(Date.now() + 4000);

      Object.defineProperty(document, 'hidden', { value: false, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));

      // No modal, no navigation
      expect(document.querySelector('[data-testid="idle-warning-modal"]')).toBeNull();
      expect(window.location.assign).not.toHaveBeenCalled();

      // After refocus, timer was reset — should not trigger for another full timeout
      vi.advanceTimersByTime(9000);
      expect(window.location.assign).not.toHaveBeenCalled();
    });
  });
});
