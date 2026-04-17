import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig(function (_a) {
    var mode = _a.mode;
    var env = loadEnv(mode, ".", "");
    return {
        plugins: [react(), tailwindcss()],
        build: {
            outDir: "dist",
            emptyOutDir: true,
        },
        server: {
            proxy: {
                "/api": {
                    target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000",
                    changeOrigin: true,
                },
            },
        },
        test: {
            environment: "jsdom",
            setupFiles: "./src/test/setup.ts",
        },
    };
});
