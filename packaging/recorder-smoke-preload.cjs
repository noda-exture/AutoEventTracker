// Test-only preload: drive the real recorder and close its browser to save.
const { chromium } = require('playwright-extra');
const launch = chromium.launch.bind(chromium);
chromium.launch = async options => {
  const browser = await launch({ ...options, headless: true });
  const newContext = browser.newContext.bind(browser);
  browser.newContext = async (...args) => {
    const context = await newContext(...args);
    context.on('page', page => {
      page.once('load', async () => {
        try {
          await page.locator('#trigger').hover();
          await page.waitForTimeout(320);
          await page.locator('#choose').click();
          await page.waitForTimeout(200);
          await page.close();
        } catch (error) {
          console.error(error);
          process.exit(1);
        }
      });
    });
    return context;
  };
  return browser;
};
