import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendPort = Number(process.env.NEKO_API_PORT || process.env.NEKO_PORT || 8765);
const backend = { target: `http://127.0.0.1:${backendPort}`, changeOrigin: true };

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": backend, "/auth": backend },
  },
  test: { environment: "jsdom" },
});
