import { resolve } from "path";
import { defineConfig } from "vite";
import cssInjectedByJsPlugin from "vite-plugin-css-injected-by-js";

export default defineConfig({
  plugins: [cssInjectedByJsPlugin()],
  // Some deps reference process.env.NODE_ENV which doesn't exist in browsers
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    lib: {
      entry: resolve(__dirname, "src/index.js"),
      name: "MilkdownBundle",
      formats: ["iife"],
      fileName: () => "milkdown-bundle.js",
    },
    outDir: "dist",
    // CodeMirror is NOT externalized: even with Crepe.Feature.CodeMirror
    // disabled, Milkdown's internal imports still evaluate at bundle load
    // time, causing ReferenceError for missing IIFE globals. Bundling
    // everything avoids this. NiceGUI's copy lives in a separate scope.
  },
});
