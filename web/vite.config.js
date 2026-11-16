import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Locally the page calls the API through the Vite proxy (no CORS needed).
// On hosting set VITE_API_URL to the backend address (see web/README.md).
const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": backend,
      "/contacts": backend,
      "/health": backend,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/tests/setup.js",
    restoreMocks: true,
    unstubGlobals: true,
  },
});
