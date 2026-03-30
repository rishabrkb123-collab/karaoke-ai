import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Read the backend port written by backend/run.py.
// Falls back to 8000 if the file doesn't exist yet.
let backendPort = 8000;
try {
  const portFile = path.resolve(__dirname, "../backend/.port");
  backendPort = parseInt(fs.readFileSync(portFile, "utf8").trim(), 10);
} catch {
  // file not written yet — backend will be on 8000
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    strictPort: false, // auto-increment if 3000 is busy
    proxy: {
      "/api": {
        target: `http://localhost:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
});
