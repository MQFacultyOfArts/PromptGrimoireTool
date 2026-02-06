import { Crepe } from "@milkdown/crepe";
import "@milkdown/crepe/theme/common/style.css";
import "@milkdown/crepe/theme/frame.css";

/**
 * Create a Milkdown Crepe editor in the given root element.
 *
 * @param {HTMLElement} rootEl - DOM element to mount the editor in.
 * @param {string} initialMd - Initial markdown content.
 * @param {function} onUpdate - Callback called with (markdown: string) on content changes.
 * @returns {Promise<Crepe>} The Crepe editor instance.
 */
async function createEditor(rootEl, initialMd, onUpdate) {
  if (window.__milkdownCrepe) {
    console.error(
      "[milkdown-bundle] Crepe editor already initialized. " +
        "Multiple instances not supported in spike."
    );
    return window.__milkdownCrepe;
  }

  // Check for conflicting ProseMirror instances
  if (document.querySelector(".ProseMirror")) {
    console.error(
      "[milkdown-bundle] Existing ProseMirror instance detected. " +
        "This may cause conflicts."
    );
  }

  const crepe = new Crepe({
    root: rootEl,
    defaultValue: initialMd || "",
    features: {
      [Crepe.Feature.CodeMirror]: false,
    },
  });

  if (onUpdate) {
    crepe.on((listener) => {
      listener.markdownUpdated((ctx, markdown) => {
        onUpdate(markdown);
      });
    });
  }

  await crepe.create();
  console.log("[milkdown-bundle] Crepe editor created");

  window.__milkdownCrepe = crepe;
  return crepe;
}

// Expose globals for Python interop via ui.run_javascript()
window._createMilkdownEditor = createEditor;

window._getMilkdownMarkdown = function () {
  if (!window.__milkdownCrepe) return "";
  return window.__milkdownCrepe.getMarkdown();
};

window._setMilkdownMarkdown = function (md) {
  if (!window.__milkdownCrepe) return;
  console.warn(
    "[milkdown-bundle] setMarkdown requires editor recreation (spike limitation)"
  );
};
