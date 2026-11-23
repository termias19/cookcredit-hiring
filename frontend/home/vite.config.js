import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// A separate entry and output: building Home cannot replace Hiring's dist or PWA.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.HOME_DEV_API_ORIGIN || "http://127.0.0.1:5048";
  if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(target))
    throw new Error("Local Home API must use loopback");
  return {
    root: fileURLToPath(new URL(".", import.meta.url)),
    envDir: fileURLToPath(new URL(".", import.meta.url)),
    plugins: [react()],
    base: "/",
    define: {
      "import.meta.env.VITE_FIREBASE_AUTH_DOMAIN": JSON.stringify(
        env.VITE_FIREBASE_AUTH_DOMAIN || "cookcredit.com",
      ),
    },
    build: { outDir: "../dist-home", emptyOutDir: true },
    server: {
      host: "127.0.0.1",
      port: 53409,
      strictPort: true,
      proxy: { "/api/home": { target } },
    },
  };
});
