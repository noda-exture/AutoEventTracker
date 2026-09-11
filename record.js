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
const inputMemo = process.argv[5]; // 💡 Pythonから渡されたメモを受け取る

if (!proj || !fileName || !startUrl) {
  console.error('❌ エラー: 引数が不足しています。(project, fileName, startUrl)');
  process.exit(1);
}

// 記録用のステップ配列
let steps = [];
let windowCounter = 1;

(async () => {
  console.log(`🚀 レコーダーを起動します...`);
  console.log(`🔗 対象URL: ${startUrl}`);

  const browser = await chromium.launch({ headless: false });
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
    
    // 直前のステップと全く同じ（重複イベント）なら無視する
    const lastStep = steps[steps.length - 1];
    if (lastStep && lastStep.action === step.action && lastStep.selector === step.selector && lastStep.value === step.value) {
        return;
    }

    steps.push(step);
    console.log(`[記録] ${step.action} -> ${step.selector}`);
  });

  // 💡 新しいページ(タブ/ウィンドウ)が開くたびに監視スクリプトを注入
  context.on('page', async (newPage) => {
    // 最初のページ以外なら「別窓切り替えステップ」を自動挿入
    if (steps.length > 0) {
      const winName = `page${windowCounter++}`;
      steps.push({
        action: 'switch_window',
        value: winName,
        memo: `別ウィンドウ [${winName}] へ切り替え`
      });
      console.log(`[記録] 🔗 別ウィンドウのオープンを検知しました`);
    }

    // クライアント(ブラウザ)側で操作を監視してセレクタを自動構築するスクリプト
    await newPage.addInitScript(() => {
      if (window.__AUTOREC_INIT) return;
      window.__AUTOREC_INIT = true;

      // 🤖 【改修】より壊れにくく柔軟な文字列セレクタを生成するロジック
      const getSelector = (el) => {
        // 1. 一意なIDや属性は最優先（変更なし）
        if (el.id) return `[id="${el.id}"]`;
        if (el.getAttribute('data-testid')) return `[data-testid="${el.getAttribute('data-testid')}"]`;
        if (el.getAttribute('placeholder')) return `[placeholder="${el.getAttribute('placeholder')}"]`;
        if (el.name) return `[name="${el.name}"]`;
        if (el.getAttribute('aria-label')) return `${el.tagName.toLowerCase()}[aria-label="${el.getAttribute('aria-label')}"]`;
        
        // テキストノードを取得してクリーニング
        const text = el.innerText ? el.innerText.trim().split('\n')[0].trim() : '';
        
        // 2. テキストが存在する場合、厳格な name= ではなく、柔軟な `has-text` (部分一致) を使う
        if (text && text.length > 0 && text.length < 30) {
            // ダブルクォーテーションをエスケープ
            const cleanText = text.replace(/"/g, '\\"');
            const tag = el.tagName.toLowerCase();
            
            if (tag === 'a') return `a:has-text("${cleanText}")`;
            if (tag === 'button' || el.getAttribute('role') === 'button') return `button:has-text("${cleanText}")`;
            
            // a, button, input, select 以外の場合も、タグに紐づけたテキスト検索にする
            if (tag !== 'select' && tag !== 'input') {
                return `${tag}:has-text("${cleanText}")`;
            }
        }
        
        // 3. 最終フォールバック (タグ + 複数クラス名)
        let pathStr = el.tagName.toLowerCase();
        if (el.className && typeof el.className === 'string') {
            const classes = el.className.trim().split(/\s+/).filter(c => c).join('.');
            if (classes) pathStr += '.' + classes;
        }
        return pathStr;
      };

      // クリックイベントの監視
      document.addEventListener('click', (e) => {
        // Inputフィールドのクリックは文字入力(change)で拾うので除外
        if (e.target.tagName === 'INPUT' && (e.target.type === 'text' || e.target.type === 'password' || e.target.type === 'email')) return;
        if (e.target.tagName === 'SELECT') return;

        // 親を遡って button や a リンクを探す
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

      // フォーム入力・選択イベントの監視
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
            action: 'click', // Playwrightではチェックボックスはclick
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

  // 💡 ブラウザが閉じられた瞬間にJSONを自動保存
  browser.on('disconnected', () => {
    console.log(`\n🛑 ブラウザが閉じられました。シナリオを保存します...`);
    
    const scenarioDir = path.join(__dirname, 'project', proj, 'scenario');
    if (!fs.existsSync(scenarioDir)) {
      fs.mkdirSync(scenarioDir, { recursive: true });
    }
    
    const safeFileName = fileName.endsWith('.json') ? fileName : `${fileName}.json`;
    const savePath = path.join(scenarioDir, safeFileName);
    
    // 💡 未入力時はデフォルトの文言をセットする
    const finalMemo = inputMemo ? inputMemo : "✅ 自動レコーダーによってキャプチャされたシナリオ";

    const outputData = {
      scenario_name: safeFileName.replace('.json', ''),
      start_url: startUrl,
      memo: finalMemo,
      steps: steps
    };
    
    try {
      fs.writeFileSync(savePath, JSON.stringify(outputData, null, 2), 'utf-8');
      console.log(`✨ 保存成功: ${savePath}`);
    } catch (err) {
      console.error(`❌ 保存エラー: ${err.message}`);
    }
  });

})();