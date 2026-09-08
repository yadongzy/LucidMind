import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const here = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  publicDir: path.resolve(here, "public"),
  build: {
    outDir: path.resolve(here, "../frontend/dist"),
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      "/ws": {
        target: "http://localhost:8001",
        ws: true,
      },
      "/api": {
        target: "http://localhost:8001",
      },
      "/static": {
        target: "http://localhost:8001",
      },
    },
  },
});
