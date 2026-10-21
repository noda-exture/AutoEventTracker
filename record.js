const { chromium } = require('playwright-extra');
const stealth = require('puppeteer-extra-plugin-stealth')();
const fs = require('fs');
const path = require('path');
const { resolveRecordingViewport } = require('./recording_settings');
const { installRecorderEvents, attachRecorderToPage } = require('./recorder_events');

// ステルスプラグインを有効化
chromium.use(stealth);

const proj = process.argv[2];
const fileName = process.argv[3];
const startUrl = process.argv[4];
const inputMemo = process.argv[5] || ""; 

if (!proj || !fileName || !startUrl) {
  console.error('エラー: 引数が不足しています。(project, fileName, startUrl)');
  process.exit(1);
}

let steps = [];
let windowCounter = 1;
let isSaved = false;
let mainPage = null;
let activePageName = null;
const pageNames = new Map();
const pendingClosedPages = [];

const nextStepId = () => String(steps.length + 1).padStart(4, '0');

const registerPage = (page) => {
  if (pageNames.has(page)) return pageNames.get(page);

  const pageName = mainPage === null ? 'main' : `page${windowCounter++}`;
  if (mainPage === null) mainPage = page;
  pageNames.set(page, pageName);
  console.log(`[タブ] ${pageName} を登録しました`);
  return pageName;
};

const pushSwitchStep = (pageName) => {
  if (!pageName || activePageName === pageName) return;
  const memo = pageName === 'main'
    ? 'メインタブへ切り替え'
    : `別タブ [${pageName}] へ切り替え`;
  steps.push({
    step_id: nextStepId(),
    step_name: memo,
    action: 'switch_window',
    value: pageName,
    page_id: pageName,
    memo: memo,
  });
  activePageName = pageName;
  console.log(`[記録] switch_window -> ${pageName}`);
};

const flushClosedPages = () => {
  while (pendingClosedPages.length > 0) {
    const pageName = pendingClosedPages.shift();
    const memo = `${pageName} を閉じる`;
    steps.push({
      step_id: nextStepId(),
      step_name: memo,
      action: 'close_window',
      value: pageName,
      page_id: pageName,
      memo: memo,
    });
    if (activePageName === pageName) activePageName = null;
    console.log(`[記録] close_window -> ${pageName}`);
  }
};

(async () => {
  console.log(`レコーダーを起動します...`);
  console.log(`対象URL: ${startUrl}`);

  const viewport = resolveRecordingViewport(process.argv[6], process.argv[7]);
  console.log(`記録時の表示領域: ${viewport.width} × ${viewport.height} px`);

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport });

  //  【修正】保存処理を内部に移動し、browser.close() を確実に呼べるようにする
  const saveScenario = async () => {
    if (isSaved) return;
    isSaved = true;
    
    console.log(`\n終了操作を検知しました。シナリオを保存します...`);
    
    const requestedFileName = path.basename(`${fileName.replace(/\.json$/i, '')}.json`);
    const scenarioName = requestedFileName
      .replace(/\.json$/i, '')
      .replace(/[<>:"/\\|?*\x00-\x1f]/g, '_')
      .replace(/^\.+|\.+$/g, '') || 'scenario';
    const safeFileName = `${scenarioName}.json`;
    const scenarioDir = path.join(process.env.AET_DATA_DIR || __dirname, 'project', proj, 'scenario', scenarioName);
    if (!fs.existsSync(scenarioDir)) {
      fs.mkdirSync(scenarioDir, { recursive: true });
    }

    const savePath = path.join(scenarioDir, safeFileName);
    
    const finalMemo = inputMemo ? inputMemo : "自動レコーダーによってキャプチャされたシナリオ";

    const outputData = {
      schema_version: 2,
      tab_capture_mode: 'stable_page_id',
      scenario_name: scenarioName,
      start_url: startUrl,
      memo: finalMemo,
      recording_settings: { viewport },
      steps: steps
    };
    
    try {
      // ファイルへ書き込み
      fs.writeFileSync(savePath, JSON.stringify(outputData, null, 2), 'utf-8');
      console.log(`保存成功: ${savePath}`);
    } catch (err) {
      console.error(`保存エラー: ${err.message}`);
    }
    
    //  【重要】残存するChromeプロセスを完全にキルする
    try {
      if (browser.isConnected()) {
        await browser.close();
      }
    } catch (e) {
      // 既に閉じられている場合は無視
    }
    
    // Nodeプロセスを終了
    process.exit(0);
  };

  await context.exposeBinding('notifyNodeEvent', ({ page }, eventData) => {
    const pageName = registerPage(page);
    flushClosedPages();
    pushSwitchStep(pageName);

    let memo;
    if (eventData.action === 'scroll') {
      memo = `画面をスクロール (${eventData.value?.y ?? 0}px)`;
    } else if (eventData.action === 'hover') {
      memo = `${eventData.tag} にマウスオーバー`;
      if (eventData.text) memo += ` (${eventData.text})`;
    } else {
      memo = `${eventData.tag} を操作`;
      if (eventData.text) memo += ` (${eventData.text})`;
    }

    let step = {
      step_id: nextStepId(),
      step_name: memo,
      action: eventData.action,
      selector: eventData.selector,
      page_id: pageName,
      memo: memo,
    };
    if (eventData.value !== undefined) {
      step.value = eventData.value;
    }
    
    const lastStep = steps[steps.length - 1];
    if (
      lastStep
      && lastStep.action === 'fill'
      && step.action === 'fill'
      && lastStep.selector === step.selector
      && lastStep.page_id === step.page_id
    ) {
      lastStep.value = step.value;
      lastStep.step_name = step.step_name;
      lastStep.memo = step.memo;
      return;
    }
    if (
      lastStep
      && lastStep.action === step.action
      && lastStep.selector === step.selector
      && JSON.stringify(lastStep.value) === JSON.stringify(step.value)
    ) {
        return;
    }

    steps.push(step);
    console.log(`[記録] ${step.action} -> ${step.selector}`);
  });

  await context.addInitScript(installRecorderEvents);

  context.on('page', (newPage) => {
    attachRecorderToPage(newPage);
    const pageName = registerPage(newPage);
    console.log(`[タブ] 新しいタブ ${pageName} を検知しました`);

    newPage.on('close', () => {
      if (isSaved) return;

      const remainingPages = context.pages().filter((candidate) => !candidate.isClosed());
      if (remainingPages.length === 0) {
        void saveScenario();
        return;
      }

      pendingClosedPages.push(pageName);
    });
  });

  const page = await context.newPage();
  registerPage(page);
  activePageName = 'main';
  await page.goto(startUrl);

  context.on('close', saveScenario);
  browser.on('disconnected', saveScenario);
  
})().catch(error => {
  console.error(`レコーダー実行エラー: ${error.message}`);
  process.exit(1);
});
