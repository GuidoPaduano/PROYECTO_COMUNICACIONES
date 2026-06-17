import path from "node:path"
import { defineConfig, devices } from "@playwright/test"

const frontendPort = Number(process.env.E2E_FRONTEND_PORT || 3000)
const backendPort = Number(process.env.E2E_BACKEND_PORT || 8000)
const baseURL = process.env.E2E_BASE_URL || `http://localhost:${frontendPort}`
const backendURL = process.env.E2E_BACKEND_URL || `http://127.0.0.1:${backendPort}`
const projectRoot = path.resolve(__dirname, "..")

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: `.\\venv\\Scripts\\python.exe manage.py runserver 127.0.0.1:${backendPort}`,
      cwd: projectRoot,
      url: `${backendURL}/api/public/school-branding/?school=qa-local`,
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: `npm run dev -- -p ${frontendPort}`,
      cwd: __dirname,
      env: {
        ...process.env,
        BACKEND_API_BASE_URL: `${backendURL}/api`,
        DJANGO_API_BASE_URL: `${backendURL}/api`,
      },
      url: baseURL,
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],
})
