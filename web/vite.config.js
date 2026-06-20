import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { fileURLToPath } from "url";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@joblens/shared": path.resolve(root, "../shared"),
      "@joblens/design": path.resolve(root, "../design"),
    },
  },
  server: { port: 5173 },
});
