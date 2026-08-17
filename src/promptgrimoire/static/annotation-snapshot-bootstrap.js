// Snapshot bundle bootstrap for the annotation page.
//
// When SNAPSHOT__ENABLED is on, the NiceGUI page renders an empty
// doc-container skeleton carrying `data-snapshot-url` (a short-lived
// tokenised bundle URL) and `data-snapshot-menu-id`.  This script is
// fully declarative: it scans for such containers on load and watches
// for later ones (deferred tab renders) with a MutationObserver, so no
// JavaScript is built or injected from Python.
// See docs/design-notes/2026-08-16-initial-snapshot-delivery.md.
//
// The bundle (document HTML, highlights, tags, sidebar items) is
// fetched from the standalone snapshot service so the NiceGUI event
// loop never constructs or transmits it.  Mount order mirrors the
// non-snapshot inline init in document.py: content, text walker,
// highlights, selection handlers, sidebar items, copy protection,
// toolbar observer.  The annotation-ready marker is appended only
// after a successful mount — readiness follows the bundle, not the
// skeleton.

async function fetchSnapshotBundle(url) {
  var response = await fetch(url);
  if (!response.ok) {
    throw new Error('snapshot fetch failed: HTTP ' + response.status);
  }
  return response.json();
}

async function loadAnnotationSnapshot(cfg) {
  var container = document.getElementById(cfg.containerId);
  if (!container) return false;

  // One silent retry covers a service restart blip or a dropped
  // connection without the student ever seeing an error.
  var retryDelay = cfg.retryDelayMs === undefined ? 1500 : cfg.retryDelayMs;
  var bundle;
  try {
    try {
      bundle = await fetchSnapshotBundle(cfg.url);
    } catch (firstErr) {
      console.warn('snapshot bundle fetch failed, retrying once', firstErr);
      await new Promise(function (resolve) { setTimeout(resolve, retryDelay); });
      bundle = await fetchSnapshotBundle(cfg.url);
    }
  } catch (err) {
    console.error('snapshot bundle load failed', err);
    container.dataset.snapshotState = 'error';
    // Unmissable by design: the page shell (toolbar, tabs, sidebar) stays
    // live around this pane, so plain body text reads as "short document".
    var failed = document.createElement('div');
    failed.setAttribute('data-testid', 'snapshot-error');
    failed.setAttribute('role', 'alert');
    failed.style.cssText =
      'margin: 3rem auto; max-width: 34rem; padding: 2rem;' +
      'border: 2px solid #c62828; border-radius: 8px;' +
      'background: #ffebee; color: #b71c1c;' +
      'font-size: 1.15rem; line-height: 1.5; text-align: center;';
    var heading = document.createElement('div');
    heading.style.cssText = 'font-size: 1.4rem; font-weight: 700; margin-bottom: 0.75rem;';
    heading.textContent = '⚠️ Document not loaded';
    var body = document.createElement('div');
    body.textContent =
      'This document could not be loaded, so nothing on this page is ' +
      'showing it. Your annotations are safe on the server.';
    var reload = document.createElement('button');
    reload.setAttribute('data-testid', 'snapshot-reload');
    reload.textContent = 'Reload page';
    reload.style.cssText =
      'margin-top: 1.25rem; padding: 0.6rem 2rem; font-size: 1rem;' +
      'border: none; border-radius: 4px; cursor: pointer;' +
      'background: #c62828; color: white;';
    reload.addEventListener('click', function () { window.location.reload(); });
    failed.replaceChildren(heading, body, reload);
    container.replaceChildren(failed);
    return false;
  }

  container.innerHTML = bundle.document_html;
  window._textNodes = walkTextNodes(container);
  applyHighlights(container, bundle.highlights);
  if (typeof setupAnnotationSelection === 'function') {
    setupAnnotationSelection(cfg.containerId, function(sel) {
      if (typeof emitEvent === 'function') emitEvent('selection_made', sel);
    }, cfg.menuId);
  }

  // Hand sidebar state to the Vue component, whichever mounted first.
  var applySidebar = window._sidebarBundleApply
    && window._sidebarBundleApply[cfg.containerId];
  if (applySidebar) {
    applySidebar(bundle);
  } else {
    window.__pendingSidebarBundle = window.__pendingSidebarBundle || {};
    window.__pendingSidebarBundle[cfg.containerId] = bundle;
  }

  if (window._pendingCopyProtection) {
    setupCopyProtection(window._pendingCopyProtection);
    delete window._pendingCopyProtection;
  }
  if (typeof initToolbarObserver === 'function') {
    initToolbarObserver();
  }

  container.dataset.snapshotState = 'done';
  var ready = document.createElement('div');
  ready.setAttribute('data-testid', 'annotation-ready');
  ready.style.display = 'none';
  document.body.appendChild(ready);
  return true;
}

// Scan for snapshot containers that have not been loaded yet.  The
// data-snapshot-state marker makes the scan idempotent, so calling it
// from both the initial pass and every observer tick is safe.
function scanSnapshotContainers() {
  var pending = document.querySelectorAll(
    '[data-snapshot-url]:not([data-snapshot-state])'
  );
  pending.forEach(function(container) {
    container.dataset.snapshotState = 'loading';
    loadAnnotationSnapshot({
      url: container.dataset.snapshotUrl,
      containerId: container.id,
      menuId: container.dataset.snapshotMenuId || '',
    });
  });
}

// Self-initialise: pick up containers already in the DOM, then watch
// for ones rendered later (deferred tab panels).  Guard against double
// initialisation if the script is evaluated twice.
//
// attributes+attributeFilter is load-bearing: NiceGUI can flush the
// container element in one WS patch and its data-snapshot-url props in
// a later one, so arming can arrive as an attribute-only mutation on an
// already-attached node.  childList alone misses that (observed as a 4%
// never-loads cliff at 100-way cram load).
if (typeof window !== 'undefined' && !window._snapshotObserver) {
  scanSnapshotContainers();
  window._snapshotObserver = new MutationObserver(scanSnapshotContainers);
  window._snapshotObserver.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['data-snapshot-url'],
  });
}
