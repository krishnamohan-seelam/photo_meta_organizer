import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Unit and component tests (PMO-30): `npm test`. Files that need Node APIs opt out of jsdom with
// a `// @vitest-environment node` comment.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true,
    // A loaded machine (editor, browser, other test runs) can make a first render slow; 5 s was flaky.
    testTimeout: 20000,
    hookTimeout: 20000,
  },
})
