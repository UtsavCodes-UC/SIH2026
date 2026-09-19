import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 127.0.0.1, not "localhost": Node resolves localhost to IPv6 (::1) first, but uvicorn listens on IPv4 only
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          leaflet: ["leaflet", "react-leaflet"],
          charts: ["recharts"],
        },
      },
    },
  },
});
