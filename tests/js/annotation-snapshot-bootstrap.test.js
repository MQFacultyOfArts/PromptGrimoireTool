// Behavioural tests for annotation-snapshot-bootstrap.js.
//
// loadAnnotationSnapshot() is the client half of the snapshot delivery
// boundary: it fetches the bundle from the standalone service, mounts
// the document, applies highlights, hands sidebar state to the Vue
// component, and only then signals annotation readiness.
// See docs/design-notes/2026-08-16-initial-snapshot-delivery.md.

import { describe, test, expect, afterEach, vi } from 'vitest';

const BUNDLE = {
  document_html: '<p>The quick brown fox jumps over the lazy dog.</p>',
  highlights: { 'tag-a': [{ start_char: 4, end_char: 9, id: 'hl-1' }] },
  items: [{ id: 'hl-1', tag_key: 'tag-a' }],
  tag_options: { 'tag-a': 'Issue' },
  permissions: { can_annotate: true },
};

function mountContainer(id = 'doc-container-test') {
  const container = document.createElement('div');
  container.id = id;
  container.innerHTML = '<div data-testid="snapshot-loading">Loading…</div>';
  document.body.appendChild(container);
  return container;
}

function mockFetch(response) {
  globalThis.fetch = vi.fn().mockResolvedValue(response);
}

afterEach(() => {
  document.body.innerHTML = '';
  CSS.highlights.clear();
  delete globalThis.fetch;
  delete window._textNodes;
  delete window._sidebarBundleApply;
  delete window.__pendingSidebarBundle;
  delete window._highlightsReady;
  delete window._annotSelectionBound;
  delete window._annotSelectionBoundFor;
  vi.restoreAllMocks();
});

describe('loadAnnotationSnapshot', () => {
  test('mounts document, applies highlights, signals readiness', async () => {
    const container = mountContainer();
    mockFetch({ ok: true, json: async () => BUNDLE });

    const ok = await loadAnnotationSnapshot({
      url: 'http://snapshot.test/snapshot?t=tok',
      containerId: container.id,
      menuId: 'hl-menu-test',
    });

    expect(ok).toBe(true);
    expect(container.textContent).toContain('quick brown fox');
    expect(container.querySelector('[data-testid="snapshot-loading"]')).toBeNull();
    expect(window._textNodes.length).toBeGreaterThan(0);
    expect(CSS.highlights.size).toBeGreaterThan(0);
    expect(
      document.body.querySelector('[data-testid="annotation-ready"]'),
    ).not.toBeNull();
  });

  test('delivers sidebar bundle via hook when component already mounted', async () => {
    const container = mountContainer();
    mockFetch({ ok: true, json: async () => BUNDLE });
    const applied = [];
    window._sidebarBundleApply = { [container.id]: (b) => applied.push(b) };

    await loadAnnotationSnapshot({ url: 'u', containerId: container.id });

    expect(applied).toHaveLength(1);
    expect(applied[0].items).toEqual(BUNDLE.items);
    expect(window.__pendingSidebarBundle).toBeUndefined();
  });

  test('parks sidebar bundle when component not yet mounted', async () => {
    const container = mountContainer();
    mockFetch({ ok: true, json: async () => BUNDLE });

    await loadAnnotationSnapshot({ url: 'u', containerId: container.id });

    expect(window.__pendingSidebarBundle[container.id].items).toEqual(
      BUNDLE.items,
    );
  });

  test('fetch failure retries once, then shows error, never claims readiness', async () => {
    const container = mountContainer();
    mockFetch({ ok: false, status: 403 });

    const ok = await loadAnnotationSnapshot({
      url: 'u',
      containerId: container.id,
      retryDelayMs: 0,
    });

    expect(ok).toBe(false);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
    expect(
      container.querySelector('[data-testid="snapshot-error"]'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('[data-testid="annotation-ready"]'),
    ).toBeNull();
  });

  test('transient failure recovers on the silent retry', async () => {
    const container = mountContainer();
    globalThis.fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValue({ ok: true, json: async () => BUNDLE });

    const ok = await loadAnnotationSnapshot({
      url: 'u',
      containerId: container.id,
      retryDelayMs: 0,
    });

    expect(ok).toBe(true);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain('quick brown fox');
    expect(container.querySelector('[data-testid="snapshot-error"]')).toBeNull();
  });

  test('network rejection shows an unmissable error with a reload button', async () => {
    const container = mountContainer();
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('offline'));

    const ok = await loadAnnotationSnapshot({
      url: 'u',
      containerId: container.id,
      retryDelayMs: 0,
    });

    expect(ok).toBe(false);
    const error = container.querySelector('[data-testid="snapshot-error"]');
    expect(error).not.toBeNull();
    expect(error.textContent).toContain('annotations are safe');
    expect(error.textContent).not.toContain('Failed');
    // Must not read as body text: styled as an alert, with a real action.
    expect(error.getAttribute('role')).toBe('alert');
    expect(error.style.border).not.toBe('');
    expect(
      error.querySelector('[data-testid="snapshot-reload"]'),
    ).not.toBeNull();
  });

  test('missing container returns false without touching the DOM', async () => {
    mockFetch({ ok: true, json: async () => BUNDLE });
    const ok = await loadAnnotationSnapshot({ url: 'u', containerId: 'absent' });
    expect(ok).toBe(false);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe('scanSnapshotContainers (declarative discovery)', () => {
  function mountArmedContainer(id = 'doc-container-armed') {
    const container = mountContainer(id);
    container.dataset.snapshotUrl = 'http://snapshot.test/snapshot?t=tok';
    container.dataset.snapshotMenuId = 'hl-menu-armed';
    return container;
  }

  test('scan fetches the data-snapshot-url of an armed container', async () => {
    const container = mountArmedContainer();
    mockFetch({ ok: true, json: async () => BUNDLE });

    scanSnapshotContainers();
    // Allow the async load kicked off by the scan to complete.
    await vi.waitFor(() =>
      expect(container.dataset.snapshotState).toBe('done'),
    );

    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://snapshot.test/snapshot?t=tok',
    );
    expect(container.textContent).toContain('quick brown fox');
  });

  test('scan is idempotent: a loaded container is never fetched twice', async () => {
    const container = mountArmedContainer();
    mockFetch({ ok: true, json: async () => BUNDLE });

    scanSnapshotContainers();
    scanSnapshotContainers();
    await vi.waitFor(() =>
      expect(container.dataset.snapshotState).toBe('done'),
    );
    scanSnapshotContainers();

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  test('observer picks up a container armed AFTER it was attached', async () => {
    // NiceGUI can flush the element in one WS patch and its
    // data-snapshot-url props in a later one; discovery must fire on the
    // attribute mutation, not only on childList.
    mockFetch({ ok: true, json: async () => BUNDLE });
    const container = mountContainer('doc-container-late-armed');

    // Attached bare; armed later — attribute-only mutation.
    container.dataset.snapshotUrl = 'http://snapshot.test/snapshot?t=tok';
    container.dataset.snapshotMenuId = 'hl-menu-late';

    await vi.waitFor(() =>
      expect(container.dataset.snapshotState).toBe('done'),
    );
    expect(container.textContent).toContain('quick brown fox');
  });

  test('observer picks up a container rendered after script load', async () => {
    mockFetch({ ok: true, json: async () => BUNDLE });
    expect(window._snapshotObserver).toBeTruthy();

    const container = mountArmedContainer('doc-container-late');
    // No manual scan: the MutationObserver must discover it.
    await vi.waitFor(() =>
      expect(container.dataset.snapshotState).toBe('done'),
    );
    expect(container.textContent).toContain('quick brown fox');
  });
});
