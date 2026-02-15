/**
 * annotation-copy-protection.js — Client-side copy/cut/paste/drag/print protection.
 *
 * Blocks copying, cutting, context menu, drag, paste, and printing on
 * protected areas when enabled for an activity. Shows a Quasar toast
 * notification on blocked actions.
 *
 * Depends on Quasar (loaded by NiceGUI).
 */

/**
 * Set up copy protection event listeners on protected areas.
 *
 * @param {string} protectedSelectors - CSS selector string identifying protected areas
 *   (e.g. '#doc-container, [data-testid="respond-reference-panel"]')
 */
function setupCopyProtection(protectedSelectors) {
  // Protected areas: copy/cut/contextmenu/dragstart blocked here.
  // #doc-container = Tab 1 (Annotate) — rendered content
  // respond-reference-panel = Tab 3 (Respond) — reference cards
  // organise-columns deliberately EXCLUDED (#164) — SortableJS needs dragstart

  function isProtected(e) {
    return e.target.closest && e.target.closest(protectedSelectors);
  }

  function showToast() {
    Quasar.Notify.create({
      message: 'Copying is disabled for this activity.',
      type: 'warning',
      position: 'top-right',
      timeout: 3000,
      icon: 'content_copy',
      group: 'copy-protection'
    });
  }

  ['copy', 'cut', 'contextmenu', 'dragstart'].forEach(function(evt) {
    document.addEventListener(evt, function(e) {
      if (isProtected(e)) { e.preventDefault(); showToast(); }
    }, true);
  });

  document.addEventListener('paste', function(e) {
    if (e.target.closest && e.target.closest('#milkdown-respond-editor')) {
      e.preventDefault();
      e.stopImmediatePropagation();
      showToast();
    }
  }, true);

  // Ctrl+P / Cmd+P print intercept
  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
      e.preventDefault();
      showToast();
    }
  }, true);
}
