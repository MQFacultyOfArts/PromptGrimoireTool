import { resolve } from "path";
import { defineConfig } from "vite";
import cssInjectedByJsPlugin from "vite-plugin-css-injected-by-js";

export default defineConfig({
  plugins: [cssInjectedByJsPlugin()],
  build: {
    lib: {
      entry: resolve(__dirname, "src/index.js"),
      name: "MilkdownBundle",
      formats: ["iife"],
      fileName: () => "milkdown-bundle.js",
    },
    outDir: "dist",
    rollupOptions: {
      // Externalize CodeMirror — NiceGUI 3.6 already bundles it
      external: [/^@codemirror\//, /^@lezer\//],
      output: {
        globals: {},
      },
    },
  },
});
