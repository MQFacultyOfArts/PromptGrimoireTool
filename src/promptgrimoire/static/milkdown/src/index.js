import { Crepe } from "@milkdown/crepe";
import "@milkdown/crepe/theme/common/style.css";
import "@milkdown/crepe/theme/frame.css";

import { collab, collabServiceCtx } from "@milkdown/plugin-collab";
import * as Y from "yjs";

// --- Base64 helpers for Uint8Array <-> string transport ---

function uint8ArrayToBase64(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToUint8Array(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/**
 * Create a Milkdown Crepe editor with Yjs CRDT collaboration.
 *
 * @param {HTMLElement} rootEl - DOM element to mount the editor in.
 * @param {string} initialMd - Initial markdown content (used only if no CRDT state exists).
 * @param {function} onYjsUpdate - Callback called with (base64Update: string) on local Yjs changes.
 * @param {string} [fragmentName] - Optional XmlFragment name within the Yjs Doc. When provided,
 *   binds to the named fragment via CollabService.bindXmlFragment() instead of bindDoc().
 *   This allows multiple editors to bind to different fragments in the same Doc.
 *   When undefined (default), uses bindDoc() for backward compatibility with the spike page.
 * @returns {Promise<Crepe>} The Crepe editor instance.
 */
async function createEditor(rootEl, initialMd, onYjsUpdate, fragmentName) {
  if (window.__milkdownCrepe) {
    console.error(
      "[milkdown-bundle] Crepe editor already initialized. " +
        "Multiple instances not supported in spike."
    );
    return window.__milkdownCrepe;
  }

  if (document.querySelector(".ProseMirror")) {
    console.error(
      "[milkdown-bundle] Existing ProseMirror instance detected. " +
        "This may cause conflicts."
    );
  }

  // Create the Yjs document for CRDT state
  const ydoc = new Y.Doc();
  window.__milkdownYDoc = ydoc;

  // Use all default features — do NOT disable CodeMirror (Milkdown 7.x bug).
  const crepe = new Crepe({
    root: rootEl,
    defaultValue: initialMd || "",
  });

  // Register the collab plugin on the underlying editor BEFORE create()
  crepe.editor.use(collab);

  await crepe.create();
  console.log("[milkdown-bundle] Crepe editor created");

  // Bind the Yjs doc (or a named XmlFragment) to the collab service and connect
  crepe.editor.action((ctx) => {
    const service = ctx.get(collabServiceCtx);
    if (fragmentName) {
      const fragment = ydoc.getXmlFragment(fragmentName);
      service.bindXmlFragment(fragment).connect();
      console.log(
        `[milkdown-bundle] Yjs collab bound to XmlFragment '${fragmentName}'`
      );
    } else {
      service.bindDoc(ydoc).connect();
      console.log("[milkdown-bundle] Yjs collab bound to Doc (default)");
    }
  });

  // Observe local Yjs updates and forward to Python via callback
  if (onYjsUpdate) {
    ydoc.on("update", (update, origin) => {
      // Skip updates that came from the remote relay to avoid echo loops
      if (origin === "remote") return;
      const b64 = uint8ArrayToBase64(update);
      onYjsUpdate(b64);
    });
  }

  window.__milkdownCrepe = crepe;
  return crepe;
}

// --- Globals for Python interop via ui.run_javascript() ---

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

/**
 * Apply a remote Yjs update (base64-encoded) to the local document.
 * Called by Python's CRDT relay via ui.run_javascript().
 */
window._applyRemoteUpdate = function (b64) {
  if (!window.__milkdownYDoc) {
    console.error("[milkdown-bundle] No Yjs doc — cannot apply remote update");
    return;
  }
  const update = base64ToUint8Array(b64);
  Y.applyUpdate(window.__milkdownYDoc, update, "remote");
};

/**
 * Get the full Yjs document state as a base64-encoded update.
 * Used for full-state sync when a new client joins.
 */
window._getYjsFullState = function () {
  if (!window.__milkdownYDoc) return "";
  const state = Y.encodeStateAsUpdate(window.__milkdownYDoc);
  return uint8ArrayToBase64(state);
};
