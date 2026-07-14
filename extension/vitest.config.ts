import { defineConfig } from 'vitest/config'
import { resolve } from 'path'

export default defineConfig({
  resolve: {
    alias: {
      vscode: resolve(__dirname, 'src/__tests__/mocks/vscode.ts'),
    },
  },
  test: {
    globals: true,
    include: ['src/**/*.test.ts'],
  },
})
