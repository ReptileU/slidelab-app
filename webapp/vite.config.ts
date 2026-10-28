import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Собранная Mini App раздаётся тем же FastAPI, что и /api — относительные пути, без CORS.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8010" },
  },
  build: {
    target: "es2020",
    sourcemap: true,
    cssCodeSplit: false,
    rollupOptions: {
      // Библиотеки отдельно: меняются редко и остаются в кэше между обновлениями приложения
      output: { manualChunks: { vendor: ["react", "react-dom", "react-router-dom", "@tanstack/react-query"] } },
    },
  },
});
