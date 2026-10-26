import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const testPort = process.env.MARKETLAB_R7_TEST_API_PORT;
if (testPort && testPort !== "58007")
  throw new Error("Unsupported owned test API port");
export default defineConfig({
  plugins: [
    react(),
    {
      name: "local-mutation-origin",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (
            req.method !== "GET" &&
            req.method !== "HEAD" &&
            req.url?.startsWith("/v1/")
          ) {
            const origin = req.headers.origin;
            if (
              origin &&
              !["http://127.0.0.1:5173", "http://localhost:5173"].includes(
                origin,
              )
            ) {
              res.statusCode = 403;
              res.end("Local browser origin required");
              return;
            }
          }
          next();
        });
      },
    },
  ],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(
      ["/v1", "/health"].map((prefix) => [
        prefix,
        {
          target: `http://127.0.0.1:${testPort ?? "8000"}`,
          changeOrigin: false,
          timeout: 1_860_000,
          proxyTimeout: 1_860_000,
        },
      ]),
    ),
  },
});
