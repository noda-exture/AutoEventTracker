const fs = require('fs');
const { chromium } = require('playwright-extra');
chromium.use(require('puppeteer-extra-plugin-stealth')());
const { installRecorderEvents } = require('./recorder_events');
(async () => {
  const result = [];
  for (const headless of [true, false]) {
    const browser = await chromium.launch({ headless });
    try {
      const context = await browser.newContext();
      const events = [];
      await context.exposeBinding('notifyNodeEvent', (_, event) => events.push(event));
      await context.addInitScript(installRecorderEvents);
      const page = await context.newPage();
      await page.goto(process.argv[2]);
      await page.locator('#trigger').hover();
      await page.waitForTimeout(320);
      await page.locator('#choose').click();
      await page.waitForTimeout(100);
      if (!events.some(e => e.action === 'hover') || !events.some(e => e.action === 'click')) {
        throw new Error('Recorder did not capture hover and click');
      }
      result.push({ headless, events });
    } finally { await browser.close(); }
  }
  fs.writeFileSync(process.argv[3], JSON.stringify(result));
})().catch(error => { console.error(error); process.exitCode = 1; });
