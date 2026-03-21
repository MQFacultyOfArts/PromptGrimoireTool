import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'happy-dom',
    setupFiles: ['./tests/js/setup.js'],
    include: ['tests/js/**/*.test.js'],
    globals: true,
  },
});
