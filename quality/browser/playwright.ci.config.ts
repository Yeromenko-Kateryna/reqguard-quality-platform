import { defineConfig } from '@playwright/test';
import verifiedConfig from './playwright.config';

// Retain all RG-06B admission, test, reporter and browser settings.
// The Linux harness owns Uvicorn startup/readiness/termination explicitly.
export default defineConfig({ ...verifiedConfig, webServer: undefined });
