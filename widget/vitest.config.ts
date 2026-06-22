import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/**/*.test.ts"], // unit tests only; Playwright owns e2e/

    coverage: {
      provider: "v8",
      include: ["src/**"],
      exclude: ["src/embed.ts"], // thin auto-mount entry; exercised manually via index.html
      reporter: ["text"],
    },
  },
});
