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

async function loadAnnotationSnapshot(cfg) {
  var container = document.getElementById(cfg.containerId);
  if (!container) return false;

  var bundle;
  try {
    var response = await fetch(cfg.url);
    if (!response.ok) {
      throw new Error('snapshot fetch failed: HTTP ' + response.status);
    }
    bundle = await response.json();
  } catch (err) {
    console.error('snapshot bundle load failed', err);
    container.dataset.snapshotState = 'error';
    var failed = document.createElement('div');
    failed.setAttribute('data-testid', 'snapshot-error');
    failed.textContent = 'Failed to load the document. Reload the page to retry.';
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
if (typeof window !== 'undefined' && !window._snapshotObserver) {
  scanSnapshotContainers();
  window._snapshotObserver = new MutationObserver(scanSnapshotContainers);
  window._snapshotObserver.observe(document.body, {
    childList: true,
    subtree: true,
  });
}
