import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// Dev proxy mirrors nginx.conf. Order matters: the ingest rule must come before the broader /api rule.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api/v1/ingest": { target: "http://localhost:8001", changeOrigin: true },
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
