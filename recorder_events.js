function installRecorderEvents() {
      // A popup may keep its Window while replacing its initial Document.
      // Guard the actual event-listener owner, not the lifetime of the window.
      if (document.__AUTOREC_INIT) return;

      const getSelector = (el, { useText = true } = {}) => {
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
        for (const text of useText ? textCandidates : []) {
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

      // Capture the selector before hover handlers can change the element's text/DOM.
      // A short dwell suppresses incidental pointer crossings.
      const hasVisibleHoverMenu = (element) => {
        const menus = new Set();
        for (let current = element; current && current !== document.body;
            current = current.parentElement) {
          // Standard nested-list menus (including headers without ARIA), and
          // portalled menus connected to their trigger with aria-controls.
          if (current.matches('li, [aria-haspopup]')) {
            for (const child of current.children) {
              if (child.matches('ul, ol, [role="menu"], [role="listbox"]')) menus.add(child);
            }
          }
          for (const id of (current.getAttribute('aria-controls') || '').split(/\s+/)) {
            const controlled = id && current.getRootNode().getElementById?.(id);
            if (controlled) menus.add(controlled);
          }
        }
        return [...menus].some((menu) => {
          if (menu.contains(element)) return false;
          const style = getComputedStyle(menu);
          return style.visibility !== 'hidden' && style.visibility !== 'collapse'
            && menu.getClientRects().length > 0;
        });
      };
      let pendingHover = null;
      let hoverTimer = null;
      const flushHover = (allowOpenMenu = false) => {
        clearTimeout(hoverTimer);
        hoverTimer = null;
        const pending = pendingHover;
        if (!pending) return;
        if (Date.now() - pending.startedAt < 250
            && !(allowOpenMenu && hasVisibleHoverMenu(pending.element))) return;
        pendingHover = null;
        if (!pending.element.isConnected) return;
        emitScrollCapture();
        void window.notifyNodeEvent(pending.event);
      };
      document.addEventListener('pointerover', (event) => {
        if (event.pointerType && event.pointerType !== 'mouse') return;
        if (event.buttons) return;
        const element = event.composedPath().find((node) => node instanceof Element);
        // Preserve the trigger only for a layout-induced target change at the
        // same pointer position. Actual movement into an existing child must
        // start its own capture, even while an ancestor's dwell is pending.
        if (pendingHover && element && pendingHover.element.contains(element)
            && event.clientX === pendingHover.clientX && event.clientY === pendingHover.clientY) return;
        flushHover(true);
        clearTimeout(hoverTimer);
        pendingHover = null;
        if (!element || element === document.body || element === document.documentElement) return;
        pendingHover = {
          element,
          clientX: event.clientX,
          clientY: event.clientY,
          startedAt: Date.now(),
          event: {
            action: 'hover',
            selector: getSelector(element, { useText: false }),
            tag: element.tagName.toLowerCase(),
            text: element.innerText?.trim().substring(0, 20),
          },
        };
        hoverTimer = setTimeout(flushHover, 260);
      }, { capture: true, passive: true });
      document.addEventListener('pointerout', (event) => {
        if (pendingHover && event.relatedTarget instanceof Node
            && pendingHover.element.contains(event.relatedTarget)) return;
        flushHover(true);
        clearTimeout(hoverTimer);
        pendingHover = null;
      }, { capture: true, passive: true });

      const notifyClickFromEvent = (e) => {
        if (!e.isTrusted) return;
        flushHover(true);
        clearTimeout(hoverTimer);
        pendingHover = null;
        emitScrollCapture();
        const eventPath = e.composedPath();
        const originalTarget = eventPath.find((node) => node instanceof Element) || e.target;
        if (originalTarget.tagName === 'INPUT' && ['text', 'password', 'email'].includes(originalTarget.type)) return;
        if (originalTarget.tagName === 'SELECT') return;
        const controlLabel = eventPath.find((node) => node instanceof HTMLLabelElement && node.control);
        if (controlLabel && ['radio', 'checkbox'].includes(controlLabel.control.type)) return;

        const el = eventPath.find((node) =>
          node instanceof Element
          && (node.tagName === 'A' || node.tagName === 'BUTTON' || node.tagName === 'LABEL'
            || (node.tagName === 'INPUT' && ['button', 'submit', 'radio', 'checkbox'].includes(node.type))
            || node.getAttribute('role') === 'button')
        ) || originalTarget;

        void window.notifyNodeEvent({
          action: 'click',
          selector: getSelector(el),
          tag: el.tagName.toLowerCase(),
          text: el.innerText?.trim().substring(0, 20)
        });
      };

      document.addEventListener('pointerdown', (e) => {
        userScrollIntentUntil = Date.now() + 1000;
      }, { capture: true, passive: true });

      document.addEventListener('click', notifyClickFromEvent, true);

      const lastInputValues = new WeakMap();
      document.addEventListener('input', (e) => {
        const el = e.composedPath().find((node) =>
          node instanceof Element && ['SELECT', 'INPUT', 'TEXTAREA'].includes(node.tagName)
        ) || e.target;
        const selector = getSelector(el);

        if (el.tagName === 'SELECT') {
          void window.notifyNodeEvent({
            action: 'select', selector, value: el.value, tag: 'select'
          });
        } else if (
          (el.tagName === 'INPUT' && !['checkbox', 'radio', 'button', 'submit'].includes(el.type))
          || el.tagName === 'TEXTAREA'
        ) {
          lastInputValues.set(el, el.value);
          void window.notifyNodeEvent({
            action: 'fill', selector, value: el.value, tag: el.tagName.toLowerCase()
          });
        }
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
        } else if (el.tagName === 'INPUT' && ['checkbox', 'radio'].includes(el.type)) {
          // Native clicks (including label forwarding) are recorded above.
          // change can be trusted even when a script called input.click().
          return;
        } else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
          if (lastInputValues.has(el) && lastInputValues.get(el) === el.value) return;
          lastInputValues.set(el, el.value);
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
      document.addEventListener('scroll', (event) => {
        if (Date.now() <= userScrollIntentUntil) queueScrollCapture(event);
      }, { capture: true, passive: true });
      document.addEventListener('keydown', (e) => {
        if (['PageDown', 'PageUp', 'Home', 'End', 'ArrowDown', 'ArrowUp', ' '].includes(e.key)) {
          markUserScrollIntent();
          queueScrollCapture(e);
        }
      }, true);
      document.__AUTOREC_INIT = true;
}

function attachRecorderToPage(page, logger = console.warn) {
  const install = frame => frame.evaluate(installRecorderEvents).catch(error => {
    if (!page.isClosed() && !/Execution context was destroyed|Frame was detached|Target page.*closed/.test(error.message)) {
      logger(`[記録警告] 操作監視の初期化に失敗しました: ${error.message}`);
    }
  });
  page.on('framenavigated', frame => { void install(frame); });
  page.on('domcontentloaded', () => {
    for (const frame of page.frames()) void install(frame);
  });
  for (const frame of page.frames()) void install(frame);
}

module.exports = { installRecorderEvents, attachRecorderToPage };
