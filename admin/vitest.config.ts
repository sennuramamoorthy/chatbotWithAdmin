import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    coverage: {
      provider: "v8",
      include: ["src/**"],
      exclude: ["src/main.ts"], // thin auto-mount entry; exercised manually via index.html
      reporter: ["text"],
    },
  },
});
