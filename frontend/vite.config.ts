import { defineConfig } from "vite";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(async () => {
  const plugins = [];

  // SWC native bindings may fail to load in GitHub Actions.
  // CI builds remain stable without the SWC plugin.
  if (process.env.CI !== "true") {
    const { default: react } = await import("@vitejs/plugin-react-swc");
    plugins.push(react());
  }

  return {
    server: {
      host: "::",
      port: 8080,
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
    plugins,
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ["react", "react-dom", "react-router-dom"],
            ui: [
              "@radix-ui/react-dialog",
              "@radix-ui/react-tabs",
              "@radix-ui/react-dropdown-menu",
              "@radix-ui/react-popover",
              "@radix-ui/react-select",
              "@radix-ui/react-tooltip",
              "@radix-ui/react-toast",
            ],
            query: ["@tanstack/react-query", "@tanstack/react-table"],
            charts: ["recharts"],
            markdown: [
              "react-markdown",
              "react-syntax-highlighter",
              "highlight.js",
            ],
          },
        },
      },
    },
  };
});
