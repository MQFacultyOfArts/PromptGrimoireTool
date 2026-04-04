/**
 * annotation-card-sync.js — Toolbar height tracking.
 *
 * Card positioning and hover interaction are now handled by the Vue
 * annotation sidebar component (annotationsidebar.js).  This file
 * retains only the toolbar height observer.
 */

// --- ResizeObserver: track toolbar height for card viewport bounds ---
// Exposed as a global so init_js in document.py can call it after DOM is ready.
// Also self-invokes as best-effort for SPA navigations where elements may
// already exist when the script loads.
//
// When the toolbar lives inside a Quasar q-footer (class "q-footer"),
// q-page handles padding automatically — we only track _toolbarHeight
// for card visibility calculations.  When using the legacy fixed-div
// fallback, we also set paddingBottom on the layout wrapper.
function initToolbarObserver() {
  if (window._toolbarObserverActive) return;
  var toolbar = document.getElementById('tag-toolbar-wrapper');
  if (!toolbar) return;

  window._toolbarObserverActive = true;
  var isQuasarFooter = toolbar.classList.contains('q-footer');
  var ro = new ResizeObserver(function(entries) {
    for (var i = 0; i < entries.length; i++) {
      var h = entries[i].target.offsetHeight;
      window._toolbarHeight = h;
      if (!isQuasarFooter) {
        // Update all layout wrappers (one per rendered source tab)
        document.querySelectorAll('.annotation-layout-wrapper').forEach(function(layout) {
          layout.style.paddingBottom = h + 'px';
        });
      }
    }
  });
  ro.observe(toolbar);
}
initToolbarObserver();
