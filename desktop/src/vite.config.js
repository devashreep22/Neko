import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Development: run the backend with Start_NekoAI.bat (it opens the site once so
// your browser gets the login cookie), then `npm run dev` and open
// http://127.0.0.1:5173  (use 127.0.0.1, not "localhost": cookies are per host).
// POST requests also need:  set NEKO_EXTRA_ORIGINS=http://127.0.0.1:5173
const backend = { target: "http://127.0.0.1:8765", changeOrigin: true };

export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, proxy: { "/api": backend, "/auth": backend } },
  test: { environment: "jsdom" },
});