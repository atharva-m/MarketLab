import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const testPort = process.env.MARKETLAB_R7_TEST_API_PORT;
if (testPort && testPort !== "58007")
  throw new Error("Unsupported owned test API port");
const phase4 = process.env.MARKETLAB_PHASE4_TEST === "1";
const phase4Port = phase4 ? "55175" : "5173";
const transportDeadline = 1_860_000;
export default defineConfig({
  plugins: [
    react(),
    {
      name: "local-mutation-origin",
      configureServer(server) {
        // Node's incoming-body deadline is separate from proxy socket timeouts.
        if (server.httpServer && "requestTimeout" in server.httpServer)
          server.httpServer.requestTimeout = transportDeadline;
        server.middlewares.use((req, res, next) => {
          if (
            req.method !== "GET" &&
            req.method !== "HEAD" &&
            (req.url?.startsWith("/v1/") || req.url?.startsWith("/v2/"))
          ) {
            const origin = req.headers.origin;
            if (
              origin &&
              ![
                `http://127.0.0.1:${phase4Port}`,
                `http://localhost:${phase4Port}`,
              ].includes(origin)
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
      ["/v1", "/v2", "/health"].map((prefix) => [
        prefix,
        {
          target: `http://127.0.0.1:${phase4 ? "55176" : (testPort ?? "8000")}`,
          changeOrigin: false,
          timeout: transportDeadline,
          proxyTimeout: transportDeadline,
        },
      ]),
    ),
  },
});
