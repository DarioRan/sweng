/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

import { mockApiPlugin } from "./src/mocks/viteMockApi.ts";

// Inside Compose the backend is reachable as http://backend:8000; when running
// the dev server on the host directly, fall back to localhost.
const apiProxy = process.env.VITE_API_PROXY ?? "http://localhost:8000";

// Default on: the frontend shell is being built and reviewed against mock data (this ticket)
// before the real pipeline is wired in. Set VITE_USE_MOCKS=false to hit a real backend instead.
const useMocks = process.env.VITE_USE_MOCKS !== "false";

export default defineConfig({
  plugins: [
    react(),
    useMocks && mockApiPlugin(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon-192.png", "icon-512.png"],
      manifest: {
        name: "Repair Assistant",
        short_name: "Repair",
        description:
          "Photograph the part, ask the question, get a cited procedure from the manufacturer's manuals.",
        theme_color: "#2563eb",
        background_color: "#f8fafc",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      // The ask pipeline needs a live backend; this only caches the app shell itself.
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
        navigateFallbackDenylist: [/^\/api\//, /^\/health/],
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    host: true,
    port: 5173,
    // Polling is needed for file-change detection on bind mounts from
    // Windows and macOS hosts.
    watch: { usePolling: true },
    // In mock mode the dev-server middleware (mockApiPlugin) answers these paths directly;
    // proxying them too would race it, so the proxy only exists against a real backend.
    proxy: useMocks
      ? undefined
      : {
          "/api": apiProxy,
          "/health": apiProxy,
        },
  },
  // `npm test` (CI test-frontend job). jsdom gives components a DOM to render into.
  test: {
    environment: "jsdom",
  },
});
