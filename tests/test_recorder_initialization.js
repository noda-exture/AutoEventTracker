const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.AET_TEST_PLAIN ? 'playwright' : 'playwright-extra');
const { installRecorderEvents, attachRecorderToPage } = require('../recorder_events');
if (!process.env.AET_TEST_PLAIN) chromium.use(require('puppeteer-extra-plugin-stealth')());

const form = '<select id="year"><option>2025</option><option>2026</option></select><button id="next">Next</button>';

test('records immediate select and click in a new popup before load finishes', async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const events = [];
    const context = await browser.newContext();
    context.on('page', p => attachRecorderToPage(p));
    await context.exposeBinding('notifyNodeEvent', (_, event) => events.push(event));
    await context.addInitScript(installRecorderEvents);
    await context.route('https://recorder.test/**', async route => {
      if (route.request().url().endsWith('/slow.png')) {
        await new Promise(resolve => setTimeout(resolve, 1500));
        await route.fulfill({status: 204});
      } else {
        await route.fulfill({contentType: 'text/html', body: route.request().url().endsWith('/popup')
          ? form + '<img src="/slow.png">'
          : '<button id="open" onclick="window.open(\'/popup\')">Open</button>'});
      }
    });
    const page = await context.newPage();
    await page.goto('https://recorder.test/');
    const pending = context.waitForEvent('page');
    await page.locator('#open').click();
    const popup = await pending;
    await popup.locator('#year').selectOption({label: '2026'});
    await popup.locator('#next').click();
    await popup.waitForTimeout(100);
    assert.ok(events.some(e => e.action === 'select' && e.value === '2026'));
    assert.equal(events.filter(e => e.action === 'click' && e.selector === '[id="next"]').length, 1);
    // A later DOMContentLoaded reattachment must not duplicate listeners.
    await popup.waitForLoadState('load');
    await popup.locator('#next').click();
    await popup.waitForTimeout(100);
    assert.equal(events.filter(e => e.action === 'click' && e.selector === '[id="next"]').length, 2);
    await popup.goto('https://recorder.test/popup', {waitUntil: 'domcontentloaded'});
    await popup.locator('#year').selectOption({label: '2026'});
    await popup.locator('#next').click();
    await popup.waitForTimeout(100);
    assert.equal(events.filter(e => e.action === 'click' && e.selector === '[id="next"]').length, 3);
    await context.close();
  } finally { await browser.close(); }
});
