import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Inside Compose the backend is reachable as http://backend:8000; when running
// the dev server on the host directly, fall back to localhost.
const apiProxy = process.env.VITE_API_PROXY ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // Polling is needed for file-change detection on bind mounts from
    // Windows and macOS hosts.
    watch: { usePolling: true },
    proxy: {
      "/api": apiProxy,
      "/health": apiProxy,
    },
  },
});
