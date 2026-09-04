const { chromium } = require('playwright-extra');
const stealth = require('puppeteer-extra-plugin-stealth')();
const fs = require('fs');
const path = require('path');

// ステルスプラグインを有効化（Bot検知を突破する設定）
chromium.use(stealth);

// GUI(Python)から渡された引数を受け取る
const proj = process.argv[2];
const fileName = process.argv[3];
const startUrl = process.argv[4];

if (!proj || !fileName || !startUrl) {
  console.error('❌ エラー: 引数が不足しています。(project, fileName, startUrl)');
  process.exit(1);
}

// 記録用のステップ配列
let steps = [];
let windowCounter = 1;
let openPages = new Set(); // アクティブなページオブジェクトを直接セットで保持

(async () => {
  console.log(`🚀 レコーダーを起動します...`);
  console.log(`🔗 対象URL: ${startUrl}`);

  let browser;

  // 💡 保存処理を行う共通関数
  let isSaved = false;
  const saveScenarioAndExit = async () => {
    if (isSaved) return;
    isSaved = true;

    console.log(`\n🛑 ブラウザの終了を検知しました。シナリオを保存します...`);
    
    const scenarioDir = path.join(__dirname, 'project', proj, 'scenario');
    if (!fs.existsSync(scenarioDir)) {
      fs.mkdirSync(scenarioDir, { recursive: true });
    }
    
    const safeFileName = fileName.endsWith('.json') ? fileName : `${fileName}.json`;
    const savePath = path.join(scenarioDir, safeFileName);
    
    const outputData = {
      scenario_name: safeFileName.replace('.json', ''),
      start_url: startUrl,
      memo: "✅ 自動レコーダーによってキャプチャされたシナリオ",
      steps: steps
    };
    
    try {
      fs.writeFileSync(savePath, JSON.stringify(outputData, null, 2), 'utf-8');
      console.log(`✨ 保存成功: ${savePath}`);
    } catch (err) {
      console.error(`❌ 保存エラー: ${err.message}`);
    } finally {
      if (browser && browser.isConnected()) {
        console.log('🧹 残存しているブラウザプロセスをクリーンアップします...');
        await browser.close().catch(() => {});
      }
      process.exit(0);
    }
  };

  try {
    browser = await chromium.launch({ headless: false });
    const context = await browser.newContext();

    // 💡 Python/Node間で情報をやり取りするためのバインディング関数
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

    // ーーー 🔧 【ここが最大の変更点】今後開くすべてのタブに、一括で監視スクリプトを事前予約する ーーー
    await context.addInitScript(() => {
      if (window.__AUTOREC_INIT) return;
      window.__AUTOREC_INIT = true;

      const getSelector = (el) => {
        if (el.id) return `[id="${el.id}"]`;
        if (el.getAttribute('placeholder')) return `[placeholder="${el.getAttribute('placeholder')}"]`;
        if (el.getAttribute('data-testid')) return `[data-testid="${el.getAttribute('data-testid')}"]`;
        
        const text = el.innerText ? el.innerText.trim().split('\n')[0] : '';
        
        let selectorBase = el.tagName.toLowerCase();
        if (el.className && typeof el.className === 'string') {
            const classes = el.className.trim().split(/\s+/).filter(c => !c.startsWith('is-')).join('.');
            if (classes) selectorBase += '.' + classes;
        }

        if (text && text.length > 0 && text.length < 40) {
            return `${selectorBase}:has-text("${text}")`;
          }
        
        if (el.name) return `[name="${el.name}"]`;
        return selectorBase;
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
    // ーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーーー

    // 💡 新しいページ(タブ/ウィンドウ)が開くたびに走るイベント監視
    context.on('page', async (newPage) => {
      openPages.add(newPage);

      // 最初のページ以外（＝2枚目以降のタブ）なら「別窓切り替えステップ」を挿入
      if (steps.length > 0) {
        const winName = `page${windowCounter++}`;
        steps.push({
          action: 'switch_window',
          value: winName,
          memo: `別ウィンドウ [${winName}] へ切り替え`
        });
        console.log(`[記録] 🔗 別ウィンドウのオープンを検知しました: ${winName}`);
      }

      // タブのクローズ監視（ゾンビ防止）
      newPage.on('close', async () => {
        openPages.delete(newPage);
        console.log(`ℹ️ タブが閉じられました (残りアクティブタブ: ${openPages.size})`);
        if (openPages.size === 0) {
          await saveScenarioAndExit();
        }
      });
    });

    const page = await context.newPage();
    await page.goto(startUrl);

    // バックアップ用：ブラウザオブジェクト自体が切断された場合
    browser.on('disconnected', async () => {
      await saveScenarioAndExit();
    });

    // Python(GUI)側から急にタスクが切断された場合
    process.on('SIGINT', async () => {
      console.log('\n⚠️ 外部からの終了シグナルを検知しました。強制終了します...');
      if (browser) await browser.close().catch(() => {});
      process.exit(0);
    });

    // メインプロセスの維持
    while (browser && browser.isConnected()) {
      await new Promise(resolve => setTimeout(resolve, 500));
    }

  } catch (globalErr) {
    console.error(`❌ レコーダー内部で致命的な例外が発生しました: ${globalErr.message}`);
    await saveScenarioAndExit();
  }
})();