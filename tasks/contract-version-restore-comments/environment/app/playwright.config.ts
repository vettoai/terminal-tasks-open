import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/browser',
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    launchOptions: { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || '/opt/chromium/chrome-linux/chrome' },
  },
  webServer: [
    { command: 'npm start --workspace=packages/collab-server', url: 'http://127.0.0.1:1234/health', reuseExistingServer: true },
    { command: 'npm run dev -- --port 5173', url: 'http://127.0.0.1:5173', reuseExistingServer: true },
  ],
})
