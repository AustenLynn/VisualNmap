import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // changeOrigin stays false so the backend's Origin check sees matching Host and Origin headers.
    proxy: { "/api": { target: "http://127.0.0.1:8765", ws: true, changeOrigin: false } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
