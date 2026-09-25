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

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();

  //  【修正】保存処理を内部に移動し、browser.close() を確実に呼べるようにする
  const saveScenario = async () => {
    if (isSaved) return;
    isSaved = true;
    
    console.log(`\n終了操作を検知しました。シナリオを保存します...`);
    
    const scenarioDir = path.join(__dirname, 'project', proj, 'scenario');
    if (!fs.existsSync(scenarioDir)) {
      fs.mkdirSync(scenarioDir, { recursive: true });
    }
    
    const safeFileName = fileName.endsWith('.json') ? fileName : `${fileName}.json`;
    const savePath = path.join(scenarioDir, safeFileName);
    
    const finalMemo = inputMemo ? inputMemo : "自動レコーダーによってキャプチャされたシナリオ";

    const outputData = {
      schema_version: 2,
      tab_capture_mode: 'stable_page_id',
      scenario_name: safeFileName.replace('.json', ''),
      start_url: startUrl,
      memo: finalMemo,
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
      && lastStep.action === step.action
      && lastStep.selector === step.selector
      && JSON.stringify(lastStep.value) === JSON.stringify(step.value)
    ) {
        return;
    }

    steps.push(step);
    console.log(`[記録] ${step.action} -> ${step.selector}`);
  });

  await context.addInitScript(() => {
      if (window.__AUTOREC_INIT) return;
      window.__AUTOREC_INIT = true;

      const getSelector = (el) => {
        const escapeAttribute = (value) => String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        const querySelectorAllDeep = (selector) => {
          const matches = [];
          const roots = [document];
          for (let index = 0; index < roots.length; index += 1) {
            const root = roots[index];
            try {
              matches.push(...root.querySelectorAll(selector));
            } catch (_) {
              return [];
            }
            for (const candidate of root.querySelectorAll('*')) {
              if (candidate.shadowRoot) roots.push(candidate.shadowRoot);
            }
          }
          return matches;
        };
        const isUnique = (selector) => {
          return querySelectorAllDeep(selector).length === 1;
        };
        const getUniqueCssPath = (element) => {
          const parts = [];
          let current = element;
          while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body) {
            let part = current.tagName.toLowerCase();
            const siblings = current.parentElement
              ? Array.from(current.parentElement.children).filter((child) => child.tagName === current.tagName)
              : [];
            if (siblings.length > 1) {
              part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
            }
            parts.unshift(part);
            const selector = parts.join(' > ');
            if (isUnique(selector)) return selector;
            current = current.parentElement;
          }
          return parts.join(' > ') || element.tagName.toLowerCase();
        };

        if (el.id) return `[id="${el.id}"]`;
        if (el.getAttribute('data-testid')) return `[data-testid="${el.getAttribute('data-testid')}"]`;
        if (el.getAttribute('placeholder')) return `[placeholder="${el.getAttribute('placeholder')}"]`;
        if (el.name) return `[name="${el.name}"]`;
        if (el.getAttribute('aria-label')) return `${el.tagName.toLowerCase()}[aria-label="${el.getAttribute('aria-label')}"]`;

        if (el.tagName === 'A' && el.getAttribute('href')) {
          const rawHref = el.getAttribute('href');
          const hrefSelector = `a[href="${escapeAttribute(rawHref)}"]`;
          let containsTrackingParameters = false;

          try {
            const hrefUrl = new URL(rawHref, document.baseURI);
            const trackingKeys = [...hrefUrl.searchParams.keys()].filter((key) =>
              ['_gl', '_ga', '_gcl_au', '_fplc', 'gclid', 'fbclid', 'msclkid'].includes(key.toLowerCase())
              || key.toLowerCase().startsWith('_ga_')
              || key.toLowerCase().startsWith('utm_')
            );
            if (trackingKeys.length > 0) {
              containsTrackingParameters = true;
              const stablePrefix = `${hrefUrl.origin}${hrefUrl.pathname}`;
              const stableHrefSelector = `a[href^="${escapeAttribute(stablePrefix)}"]`;
              if (isUnique(stableHrefSelector)) return stableHrefSelector;
            }
          } catch (_) {
            // Relative or malformed URLs fall through to the text/CSS selector.
          }
          if (!containsTrackingParameters && isUnique(hrefSelector)) return hrefSelector;
        }
        
        const rawText = el.innerText ? el.innerText.trim() : '';
        const textLines = rawText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
        const normalizedText = rawText.replace(/\s+/g, ' ');
        const textCandidates = [...new Set([textLines[0], normalizedText].filter(Boolean))];
        for (const text of textCandidates) {
          if (text.length > 0 && text.length < 80) {
            const cleanText = text.replace(/"/g, '\\"');
            const tag = el.tagName.toLowerCase();
            const textTag = tag === 'a' ? 'a' : (tag === 'button' || el.getAttribute('role') === 'button' ? 'button' : tag);
            const matchingTextElements = querySelectorAllDeep(textTag).filter((candidate) =>
              (candidate.innerText || '').trim().replace(/\s+/g, ' ').includes(text)
            );
            if (tag === 'a' && matchingTextElements.length === 1) return `a:has-text("${cleanText}")`;
            if ((tag === 'button' || el.getAttribute('role') === 'button') && matchingTextElements.length === 1) {
              return `button:has-text("${cleanText}")`;
            }
            if (tag !== 'select' && tag !== 'input') {
                if (matchingTextElements.length === 1) return `${tag}:has-text("${cleanText}")`;
            }
          }
        }
        
        let pathStr = el.tagName.toLowerCase();
        if (el.className && typeof el.className === 'string') {
            const classes = el.className.trim().split(/\s+/).filter(c => c).join('.');
            if (classes) pathStr += '.' + classes;
        }
        return isUnique(pathStr) ? pathStr : getUniqueCssPath(el);
      };

      let scrollCaptureTimer = null;
      let pendingScrollTarget = null;
      let userScrollIntentUntil = 0;
      const findScrollTarget = (event) => {
        if (event.type === 'scroll') {
          return event.target === document ? document.scrollingElement : event.target;
        }
        const path = event.composedPath?.() || [event.target];
        return path.find((node) => {
          if (!(node instanceof Element)) return false;
          const style = getComputedStyle(node);
          return /(auto|scroll|overlay)/.test(style.overflowY)
            && node.scrollHeight > node.clientHeight + 2;
        }) || document.scrollingElement;
      };
      const emitScrollCapture = () => {
        clearTimeout(scrollCaptureTimer);
        scrollCaptureTimer = null;
        const target = pendingScrollTarget;
        if (!target) return;
        pendingScrollTarget = null;
        const isPage = target === document.scrollingElement
          || target === document.documentElement || target === document.body;
        void window.notifyNodeEvent({
          action: 'scroll',
          selector: isPage ? null : getSelector(target),
          value: {
            x: Math.round(isPage ? window.scrollX : target.scrollLeft),
            y: Math.round(isPage ? window.scrollY : target.scrollTop),
          },
          tag: isPage ? 'page' : target.tagName.toLowerCase(),
        });
      };
      const queueScrollCapture = (event) => {
        pendingScrollTarget = findScrollTarget(event);
        clearTimeout(scrollCaptureTimer);
        scrollCaptureTimer = setTimeout(emitScrollCapture, 400);
      };

      document.addEventListener('click', (e) => {
        emitScrollCapture();
        const eventPath = e.composedPath();
        const originalTarget = eventPath.find((node) => node instanceof Element) || e.target;
        if (originalTarget.tagName === 'INPUT' && ['text', 'password', 'email'].includes(originalTarget.type)) return;
        if (originalTarget.tagName === 'SELECT') return;

        const el = eventPath.find((node) =>
          node instanceof Element
          && (node.tagName === 'A' || node.tagName === 'BUTTON' || node.getAttribute('role') === 'button')
        ) || originalTarget;

        void window.notifyNodeEvent({
          action: 'click',
          selector: getSelector(el),
          tag: el.tagName.toLowerCase(),
          text: el.innerText?.trim().substring(0, 20)
        });
      }, true);

      document.addEventListener('change', (e) => {
        emitScrollCapture();
        const el = e.composedPath().find((node) =>
          node instanceof Element && ['SELECT', 'INPUT', 'TEXTAREA'].includes(node.tagName)
        ) || e.target;
        const selector = getSelector(el);
        
        if (el.tagName === 'SELECT') {
          void window.notifyNodeEvent({
            action: 'select',
            selector: selector,
            value: el.value,
            tag: 'select'
          });
        } else if (el.tagName === 'INPUT' && (el.type === 'checkbox' || el.type === 'radio')) {
          void window.notifyNodeEvent({
            action: 'click', 
            selector: selector,
            tag: 'input'
          });
        } else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
          void window.notifyNodeEvent({
            action: 'fill',
            selector: selector,
            value: el.value,
            tag: el.tagName.toLowerCase()
          });
        }
      }, true);

      const markUserScrollIntent = () => { userScrollIntentUntil = Date.now() + 1000; };
      document.addEventListener('wheel', (event) => {
        markUserScrollIntent();
        queueScrollCapture(event);
      }, { capture: true, passive: true });
      document.addEventListener('touchmove', (event) => {
        markUserScrollIntent();
        queueScrollCapture(event);
      }, { capture: true, passive: true });
      document.addEventListener('pointerdown', markUserScrollIntent, { capture: true, passive: true });
      document.addEventListener('scroll', (event) => {
        if (Date.now() <= userScrollIntentUntil) queueScrollCapture(event);
      }, { capture: true, passive: true });
      document.addEventListener('keydown', (e) => {
        if (['PageDown', 'PageUp', 'Home', 'End', 'ArrowDown', 'ArrowUp', ' '].includes(e.key)) {
          markUserScrollIntent();
          queueScrollCapture(e);
        }
      }, true);
  });

  context.on('page', (newPage) => {
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
  
})();
