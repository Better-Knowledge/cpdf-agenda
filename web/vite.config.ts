import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Em produção a SPA vive em /app no mesmo domínio da API (sem CORS).
// Em dev, o proxy repassa as rotas da API para o protótipo local.
const ROTAS_API = [
  "/services",
  "/resources",
  "/availability",
  "/slots",
  "/appointments",
  "/agenda",
  "/health",
];

export default defineConfig({
  base: "/app/",
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      ROTAS_API.map((rota) => [
        rota,
        { target: process.env.API_URL ?? "http://localhost:8100", changeOrigin: true },
      ]),
    ),
  },
});
