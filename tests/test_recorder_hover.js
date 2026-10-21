const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { installRecorderEvents } = require('../recorder_events');

const fixture = `
<style>
body { margin: 0; padding: 80px; }
#menu { width: 200px; }
#trigger, #nested { display: block; width: 200px; height: 40px; }
#submenu, #leaf { display: none; }
#menu:hover #submenu { display: block; }
#submenu:hover #leaf { display: block; }
#dynamic { margin-top: 100px; width: 200px; height: 40px; }
</style>
<div id="menu"><div id="trigger">Menu</div><div id="submenu">
<div id="nested">Nested</div><button id="leaf" onclick="window.chosen='css'">Choose</button>
</div></div>
<div id="dynamic" onmouseenter="if (!document.getElementById('generated')) {
const button = document.createElement('button'); button.id = 'generated';
button.textContent = 'Generated'; button.onclick = () => window.chosen = 'js'; this.append(button);
}" onmouseleave="document.getElementById('generated')?.remove()">Dynamic</div>`;

test('records and replays CSS nested menus and dynamically generated items', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const kind of ['css', 'js']) {
      const events = [];
      const context = await browser.newContext();
      await context.exposeBinding('notifyNodeEvent', (_, event) => events.push(event));
      await context.addInitScript(installRecorderEvents);
      const page = await context.newPage();
      await page.goto('data:text/html;charset=utf-8,' + encodeURIComponent(fixture));
      if (kind === 'css') {
        await page.locator('#trigger').hover();
        await page.waitForTimeout(320);
        await page.locator('#nested').hover();
        await page.waitForTimeout(320);
        await page.locator('#leaf').click();
      } else {
        await page.locator('#dynamic').hover();
        await page.waitForTimeout(320);
        await page.locator('#generated').click();
      }
      await page.waitForTimeout(50);
      assert.equal(await page.evaluate(() => window.chosen), kind);
      const actions = events.filter(event => ['hover', 'click'].includes(event.action));
      assert.ok(actions.some(event => event.action === 'hover'));
      if (kind === 'css') {
        assert.deepEqual(actions.filter(event => event.action === 'hover').map(event => event.selector),
          ['[id="trigger"]', '[id="nested"]']);
      }
      const replay = await browser.newPage();
      await replay.goto('data:text/html;charset=utf-8,' + encodeURIComponent(fixture));
      for (const event of actions) {
        await replay.locator(event.selector)[event.action]({ timeout: 2000 });
      }
      assert.equal(await replay.evaluate(() => window.chosen), kind);
      await replay.close();
      await context.close();
    }
  } finally { await browser.close(); }
});

test('ignores brief crossings and touch pointer events', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const events = [];
    const context = await browser.newContext();
    await context.exposeBinding('notifyNodeEvent', (_, event) => events.push(event));
    await context.addInitScript(installRecorderEvents);
    const page = await context.newPage();
    await page.goto('data:text/html;charset=utf-8,' + encodeURIComponent(fixture));
    await page.locator('#trigger').hover();
    await page.mouse.move(5, 5);
    await page.waitForTimeout(320);
    await page.locator('#trigger').dispatchEvent('pointerover', { pointerType: 'touch' });
    await page.waitForTimeout(320);
    assert.deepEqual(events.filter(event => event.action === 'hover'), []);
  } finally { await browser.close(); }
});

// Mirrors the observed header structure: a navigation list, a trigger link,
// and a hidden nested list. The footer repeats the trigger text and href.
const productMenuFixture = (mode) => `
<style>
body { margin: 0; padding: 80px; }
nav > ul { display: flex; width: 700px; padding: 25px; margin: 0; list-style: none; }
nav > ul > li { position: relative; list-style: none; }
nav a { display: block; padding: 12px 20px; }
.level-01-cont { position: absolute; top: 100%; left: 0; width: 350px;
  padding: 12px; margin: 0; list-style: none; background: #eee; display: none; }
${mode === 'css' ? '.level-01-trigger:hover > ul { display: block; }' : ''}
footer { margin-top: 500px; }
</style>
<header><nav><ul>
<li><a href="/service">プロフェッショナルサービス</a></li>
<li class="level-01-trigger" ${mode === 'js' ? `onmouseenter="this.querySelector('ul').style.display='block'" onmouseleave="this.querySelector('ul').style.display='none'"` : ''}>
<a href="/product">プロダクト</a><ul class="level-01-cont">
<li><a href="/product/semaia">SEMAIA — AI分析エージェント</a></li>
<li><a href="/product/wiiisdom" onclick="event.preventDefault(); window.chosen='wiiisdom'">Wiiisdom — BI運用・品質管理</a></li>
</ul></li><li><a href="/case">実績・事例</a></li>
</ul></nav></header>
<footer><ul><li><a href="/product">プロダクト</a></li></ul></footer>`;

for (const mode of ['css', 'js']) {
  for (const pause of [0, 320]) {
    test(`product menu preserves its trigger after crossing navigation (${mode}, dwell ${pause}ms)`, async () => {
      const browser = await chromium.launch({ headless: true });
      try {
        const events = [];
        const context = await browser.newContext();
        await context.exposeBinding('notifyNodeEvent', (_, event) => events.push(event));
        await context.addInitScript(installRecorderEvents);
        const page = await context.newPage();
        const html = productMenuFixture(mode);
        await page.goto('data:text/html;charset=utf-8,' + encodeURIComponent(html));
        await page.locator('nav > ul').hover({ position: { x: 4, y: 4 } });
        await page.locator('nav > ul > li > a[href="/product"]').hover();
        if (pause) await page.waitForTimeout(pause);
        await page.locator('.level-01-cont').hover({ position: { x: 4, y: 4 } });
        await page.waitForTimeout(320);
        await page.locator('a[href="/product/wiiisdom"]').click();
        await page.waitForTimeout(50);
        const actions = events.filter(event => ['hover', 'click'].includes(event.action));
        assert.ok(actions.some(event => event.action === 'hover' && event.text === 'プロダクト'),
          `Missing menu trigger: ${JSON.stringify(actions)}`);
        const replay = await browser.newPage();
        await replay.goto('data:text/html;charset=utf-8,' + encodeURIComponent(html));
        for (const event of actions) {
          await replay.locator(event.selector)[event.action]({ timeout: 2000 });
        }
        assert.equal(await replay.evaluate(() => window.chosen), 'wiiisdom');
        await replay.close();
        await context.close();
      } finally { await browser.close(); }
    });
  }
}

test('retains a quick hover that opens an aria-controls menu outside the trigger', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const events = [];
    const context = await browser.newContext();
    await context.exposeBinding('notifyNodeEvent', (_, event) => events.push(event));
    await context.addInitScript(installRecorderEvents);
    const page = await context.newPage();
    const html = `<button id="trigger" aria-controls="popup"
      onmouseenter="document.getElementById('popup').hidden=false">Products</button>
      <div id="popup" hidden><button id="choice" onclick="window.chosen=true">Choose</button></div>`;
    await page.goto('data:text/html;charset=utf-8,' + encodeURIComponent(html));
    await page.locator('#trigger').hover();
    await page.locator('#choice').click();
    await page.waitForTimeout(50);
    assert.equal(events[0]?.action, 'hover');
    assert.equal(events[0]?.selector, '[id="trigger"]');
    const replay = await browser.newPage();
    await replay.goto('data:text/html;charset=utf-8,' + encodeURIComponent(html));
    for (const event of events) {
      await replay.locator(event.selector)[event.action]({ timeout: 2000 });
    }
    assert.equal(await replay.evaluate(() => window.chosen), true);
  } finally { await browser.close(); }
});

test('records one login click without a repeated fill on blur', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const events = [];
    const context = await browser.newContext();
    await context.exposeBinding('notifyNodeEvent', (_, event) => events.push(event));
    await context.addInitScript(installRecorderEvents);
    const page = await context.newPage();
    await page.goto('data:text/html,' + encodeURIComponent('<input id="password" type="password"><button id="login">Login</button>'));
    await page.locator('#password').fill('fixture-value');
    await page.locator('#login').click();
    await page.waitForTimeout(100);
    assert.equal(events.filter(e => e.action === 'fill').length, 1);
    assert.equal(events.filter(e => e.action === 'click').length, 1);
    assert.deepEqual(events.filter(e => ['fill', 'click'].includes(e.action)).map(e => e.action), ['fill', 'click']);
    await page.locator('#login').press('Enter');
    await page.waitForTimeout(100);
    assert.equal(events.filter(e => e.action === 'click').length, 2);
    await context.close();
  } finally { await browser.close(); }
});

test('does not record site-generated hidden radio clicks', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const events = [];
    const context = await browser.newContext();
    await context.exposeBinding('notifyNodeEvent', (_, event) => events.push(event));
    await context.addInitScript(installRecorderEvents);
    const page = await context.newPage();
    await page.goto('data:text/html,' + encodeURIComponent('<input id="plan" type="radio" style="visibility:hidden"><button id="user">User</button>'));
    await page.evaluate(() => document.getElementById('plan').click());
    await page.locator('#user').click();
    await page.waitForTimeout(100);
    assert.deepEqual(events.filter(e => e.action === 'click').map(e => e.selector), ['[id="user"]']);
    await context.close();
  } finally { await browser.close(); }
});

test('records native label radio selection once and keyboard checkbox activation', async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const events=[];
    const context=await browser.newContext();
    await context.exposeBinding('notifyNodeEvent',(_,e)=>events.push(e));
    await context.addInitScript(installRecorderEvents);
    const page=await context.newPage();
    await page.goto('data:text/html,'+encodeURIComponent('<input type="radio" id="radio"><label for="radio">Choose</label><input type="checkbox" id="check">'));
    await page.locator('label').click();
    await page.locator('#check').press('Space');
    await page.waitForTimeout(100);
    assert.deepEqual(events.filter(e=>e.action==='click').map(e=>e.selector),['[id="radio"]','[id="check"]']);
    await context.close();
  } finally {await browser.close();}
});
