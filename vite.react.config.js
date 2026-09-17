import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    emptyOutDir: false,
    outDir: "app/static/react",
    rollupOptions: {
      input: "app/static/react/coramail-react.js",
      output: {
        entryFileNames: "coramail-react.bundle.js",
        chunkFileNames: "coramail-react.[name].js",
        assetFileNames: "coramail-react.[name][extname]",
      },
    },
  },
});
