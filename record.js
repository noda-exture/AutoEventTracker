const { chromium } = require('playwright-extra');
const stealth = require('puppeteer-extra-plugin-stealth')();
const fs = require('fs');
const path = require('path');

// ステルスプラグインを有効化
chromium.use(stealth);

const proj = process.argv[2];
const fileName = process.argv[3];
const startUrl = process.argv[4];
const inputMemo = process.argv[5] || ""; 

if (!proj || !fileName || !startUrl) {
  console.error('❌ エラー: 引数が不足しています。(project, fileName, startUrl)');
  process.exit(1);
}

let steps = [];
let windowCounter = 1;
let isSaved = false;

(async () => {
  console.log(`🚀 レコーダーを起動します...`);
  console.log(`🔗 対象URL: ${startUrl}`);

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();

  // 💡 【修正】保存処理を内部に移動し、browser.close() を確実に呼べるようにする
  const saveScenario = async () => {
    if (isSaved) return;
    isSaved = true;
    
    console.log(`\n🛑 終了操作を検知しました。シナリオを保存します...`);
    
    const scenarioDir = path.join(__dirname, 'project', proj, 'scenario');
    if (!fs.existsSync(scenarioDir)) {
      fs.mkdirSync(scenarioDir, { recursive: true });
    }
    
    const safeFileName = fileName.endsWith('.json') ? fileName : `${fileName}.json`;
    const savePath = path.join(scenarioDir, safeFileName);
    
    const finalMemo = inputMemo ? inputMemo : "✅ 自動レコーダーによってキャプチャされたシナリオ";

    const outputData = {
      scenario_name: safeFileName.replace('.json', ''),
      start_url: startUrl,
      memo: finalMemo,
      steps: steps
    };
    
    try {
      // ファイルへ書き込み
      fs.writeFileSync(savePath, JSON.stringify(outputData, null, 2), 'utf-8');
      console.log(`✨ 保存成功: ${savePath}`);
    } catch (err) {
      console.error(`❌ 保存エラー: ${err.message}`);
    }
    
    // 💡 【重要】残存するChromeプロセスを完全にキルする
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

  await context.exposeFunction('notifyNodeEvent', (eventData) => {
    let memo = `${eventData.tag} を操作`;
    if (eventData.text) memo += ` (${eventData.text})`;

    let step = {
      action: eventData.action,
      selector: eventData.selector,
      memo: memo,
    };
    if (eventData.value !== undefined) {
      step.value = eventData.value;
    }
    
    const lastStep = steps[steps.length - 1];
    if (lastStep && lastStep.action === step.action && lastStep.selector === step.selector && lastStep.value === step.value) {
        return;
    }

    steps.push(step);
    console.log(`[記録] ${step.action} -> ${step.selector}`);
  });

  context.on('page', async (newPage) => {
    if (steps.length > 0) {
      const winName = `page${windowCounter++}`;
      steps.push({
        action: 'switch_window',
        value: winName,
        memo: `別ウィンドウ [${winName}] へ切り替え`
      });
      console.log(`[記録] 🔗 別ウィンドウのオープンを検知しました`);
    }

    await newPage.addInitScript(() => {
      if (window.__AUTOREC_INIT) return;
      window.__AUTOREC_INIT = true;

      const getSelector = (el) => {
        if (el.id) return `[id="${el.id}"]`;
        if (el.getAttribute('data-testid')) return `[data-testid="${el.getAttribute('data-testid')}"]`;
        if (el.getAttribute('placeholder')) return `[placeholder="${el.getAttribute('placeholder')}"]`;
        if (el.name) return `[name="${el.name}"]`;
        if (el.getAttribute('aria-label')) return `${el.tagName.toLowerCase()}[aria-label="${el.getAttribute('aria-label')}"]`;
        
        const text = el.innerText ? el.innerText.trim().split('\n')[0].trim() : '';
        if (text && text.length > 0 && text.length < 30) {
            const cleanText = text.replace(/"/g, '\\"');
            const tag = el.tagName.toLowerCase();
            if (tag === 'a') return `a:has-text("${cleanText}")`;
            if (tag === 'button' || el.getAttribute('role') === 'button') return `button:has-text("${cleanText}")`;
            if (tag !== 'select' && tag !== 'input') {
                return `${tag}:has-text("${cleanText}")`;
            }
        }
        
        let pathStr = el.tagName.toLowerCase();
        if (el.className && typeof el.className === 'string') {
            const classes = el.className.trim().split(/\s+/).filter(c => c).join('.');
            if (classes) pathStr += '.' + classes;
        }
        return pathStr;
      };

      document.addEventListener('click', (e) => {
        if (e.target.tagName === 'INPUT' && (e.target.type === 'text' || e.target.type === 'password' || e.target.type === 'email')) return;
        if (e.target.tagName === 'SELECT') return;

        let el = e.target;
        while (el && el !== document.body) {
          if (el.tagName === 'A' || el.tagName === 'BUTTON' || el.getAttribute('role') === 'button') break;
          el = el.parentElement;
        }
        if (!el || el === document.body) el = e.target;

        window.notifyNodeEvent({
          action: 'click',
          selector: getSelector(el),
          tag: el.tagName.toLowerCase(),
          text: el.innerText?.trim().substring(0, 20)
        });
      }, true);

      document.addEventListener('change', (e) => {
        const el = e.target;
        const selector = getSelector(el);
        
        if (el.tagName === 'SELECT') {
          window.notifyNodeEvent({
            action: 'select',
            selector: selector,
            value: el.value,
            tag: 'select'
          });
        } else if (el.tagName === 'INPUT' && (el.type === 'checkbox' || el.type === 'radio')) {
          window.notifyNodeEvent({
            action: 'click', 
            selector: selector,
            tag: 'input'
          });
        } else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
          window.notifyNodeEvent({
            action: 'fill',
            selector: selector,
            value: el.value,
            tag: el.tagName.toLowerCase()
          });
        }
      }, true);
    });
  });

  const page = await context.newPage();
  await page.goto(startUrl);

  // 💡 【修正】メインのページ（タブ）が閉じられた時点で即座に保存処理を走らせる
  page.on('close', saveScenario);
  context.on('close', saveScenario);
  browser.on('disconnected', saveScenario);
  
})();