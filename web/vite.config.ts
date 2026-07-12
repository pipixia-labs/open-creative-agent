import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/static/",
  plugins: [react()],
  build: {
    outDir: "../server/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:9502",
      "/chat": "http://127.0.0.1:9502",
      "/file": "http://127.0.0.1:9502",
    },
  },
});
