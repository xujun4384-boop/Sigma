// Sigma Browser Controller - Content Script
// 注入到普通网页中，接收 background.js 发来的命令并直接操作 DOM

(function () {
  'use strict';

  if (window.__sigmaBrowserControllerInjected) return;
  window.__sigmaBrowserControllerInjected = true;

  // ═══════════════════════════════════════════════
  // 日志系统（保留最近 200 条，可通过 get_bridge_logs 获取）
  // ═══════════════════════════════════════════════
  const _bridgeLogs = [];
  const MAX_BRIDGE_LOGS = 200;

  function _log(level, msg, extra = null) {
    const entry = {
      ts: Date.now(),
      level,
      msg,
      url: location.href.slice(0, 200),
    };
    if (extra) entry.extra = extra;
    _bridgeLogs.push(entry);
    if (_bridgeLogs.length > MAX_BRIDGE_LOGS) _bridgeLogs.shift();

    // 发送到 background.js 持久化（跨页面导航不丢失）
    try {
      chrome.runtime.sendMessage({ type: 'bridge_log', entry });
    } catch (_) { /* ignore */ }

    const prefix = `[Sigma Content] [${level}]`;
    if (extra) {
      console.log(prefix, msg, extra);
    } else {
      console.log(prefix, msg);
    }
  }

  function _logInfo(msg, extra) { _log('INFO', msg, extra); }
  function _logWarn(msg, extra) { _log('WARN', msg, extra); }
  function _logError(msg, extra) { _log('ERROR', msg, extra); }

  function _logAction(action, params, result) {
    const extra = {
      action,
      params: params ? JSON.stringify(params).slice(0, 500) : '',
    };
    if (result) {
      if (typeof result === 'object') {
        if (result.clicked !== undefined) extra.clicked = result.clicked;
        if (result.navigationDetected !== undefined) extra.navigationDetected = result.navigationDetected;
        if (result.stability) extra.stability = result.stability;
        if (result.needsSnapshot) extra.needsSnapshot = result.needsSnapshot;
        if (result.alreadySet) extra.alreadySet = true;
        if (result.strategy) extra.strategy = result.strategy;
        if (result.error) extra.error = String(result.error).slice(0, 300);
        if (result.message) extra.message = String(result.message).slice(0, 200);
      }
    }
    _logInfo(`${action}`, extra);
  }

  // ═══════════════════════════════════════════════
  // 核心状态
  // ═══════════════════════════════════════════════

  let elementRegistry = new Map();
  let elementRefs = new WeakMap();
  let refSelectors = new Map();    // ref -> selector 备用，ref失效时通过selector回退查找
  let nextElementId = 1;
  let snapshotRects = new Map();   // ref -> {x,y,width,height} 快照时的页面坐标，用于点击前漂移校验
  let currentSnapshotId = 0;      // 每次 snapshot 递增，click 需携带一致的 snapshotId

  const SKIPPED_TAGS = new Set(['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT', 'META', 'LINK']);
  const INTERACTIVE_TAGS = new Set(['A', 'BUTTON', 'INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'SUMMARY']);
  const INTERACTIVE_ROLES = new Set([
    'button', 'link', 'checkbox', 'radio', 'textbox', 'searchbox', 'combobox',
    'listbox', 'option', 'tab', 'menuitem', 'switch', 'slider', 'spinbutton'
  ]);

  function resetElementRegistry() {
    elementRegistry = new Map();
    elementRefs = new WeakMap();
    refSelectors = new Map();
    nextElementId = 1;
    snapshotRects = new Map();
    currentSnapshotId += 1;
  }

  function trimText(text, maxLength = 160) {
    const normalized = String(text || '').replace(/\s+/g, ' ').trim();
    if (normalized.length <= maxLength) return normalized;
    return normalized.slice(0, maxLength - 1) + '…';
  }

  function getRole(el) {
    return (el.getAttribute('role') || '').trim().toLowerCase();
  }

  function isVisible(el) {
    if (!el || !el.isConnected) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function hasClickHandler(el) {
    if (!el) return false;
    if (typeof el.onclick === 'function') return true;
    const cursor = window.getComputedStyle(el).cursor;
    return cursor === 'pointer';
  }

  function isClickable(el) {
    if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
    const style = window.getComputedStyle(el);
    if (style.pointerEvents === 'none') return false;
    if (INTERACTIVE_TAGS.has(el.tagName)) return true;
    if (INTERACTIVE_ROLES.has(getRole(el))) return true;
    if (el.isContentEditable) return true;
    if (el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1') return true;
    if (style.cursor === 'pointer') return true;
    if (typeof el.onclick === 'function') return true;
    return false;
  }

  function isInViewport(el) {
    const rect = el.getBoundingClientRect();
    return rect.bottom > 0 && rect.right > 0 &&
           rect.top < window.innerHeight && rect.left < window.innerWidth;
  }

  function isShadowHost(el) {
    return Boolean(el && el.shadowRoot);
  }

  function getElementDepthContext(el) {
    let insideShadow = false;
    let insideIframe = false;
    let node = el;
    while (node) {
      if (node.nodeType === Node.DOCUMENT_FRAGMENT_NODE && node.host) {
        insideShadow = true;
        node = node.host;
      } else if (node.nodeType === Node.DOCUMENT_NODE) {
        const win = node.defaultView;
        if (win && win !== window) {
          insideIframe = true;
          node = win.frameElement;
        } else {
          break;
        }
      } else {
        node = node.parentNode;
      }
    }
    return { insideShadow, insideIframe };
  }

  function isInteractive(el) {
    if (!el || SKIPPED_TAGS.has(el.tagName)) return false;
    if (INTERACTIVE_TAGS.has(el.tagName)) return true;
    if (el.isContentEditable) return true;
    if (el.hasAttribute('tabindex')) return true;
    if (INTERACTIVE_ROLES.has(getRole(el))) return true;
    return hasClickHandler(el);
  }

  function getClickableAncestor(el) {
    let node = el;
    while (node && node !== document.body && node.nodeType === Node.ELEMENT_NODE) {
      if (isInteractive(node)) return node;
      node = node.parentElement;
    }
    return el;
  }

  function normalizeMatchText(text) {
    return String(text || '').replace(/\s+/g, '').toLowerCase();
  }

  function registerElement(el) {
    if (!el || !el.isConnected) return null;
    const existing = elementRefs.get(el);
    if (existing) return existing;
    const ref = '@e' + nextElementId++;
    elementRefs.set(el, ref);
    elementRegistry.set(ref, el);
    refSelectors.set(ref, generateSelector(el));  // 记录selector用于ref失效时回退
    // 记录快照时的页面坐标，用于点击前漂移校验
    const rect = el.getBoundingClientRect();
    snapshotRects.set(ref, {
      x: rect.x + window.scrollX,
      y: rect.y + window.scrollY,
      width: rect.width,
      height: rect.height,
    });
    return ref;
  }

  function generateSelector(el) {
    if (!el) return '';
    if (el.id) return '#' + CSS.escape(el.id);
    if (el.getAttribute('name')) {
      return `${el.tagName.toLowerCase()}[name="${CSS.escape(el.getAttribute('name'))}"]`;
    }
    if (el.getAttribute('aria-label')) {
      return `${el.tagName.toLowerCase()}[aria-label="${CSS.escape(el.getAttribute('aria-label'))}"]`;
    }
    if (el.className && typeof el.className === 'string') {
      const cls = el.className.split(/\s+/).filter(Boolean).slice(0, 3).map((name) => CSS.escape(name)).join('.');
      if (cls) return el.tagName.toLowerCase() + '.' + cls;
    }
    const path = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE && path.length < 7) {
      let name = node.nodeName.toLowerCase();
      const parent = node.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter((c) => c.nodeName === node.nodeName);
        if (siblings.length > 1) {
          const index = Array.from(parent.children).indexOf(node) + 1;
          name += `:nth-child(${index})`;
        }
      }
      path.unshift(name);
      node = parent;
    }
    return path.join(' > ');
  }

  function elementLabel(el) {
    const aria = el.getAttribute('aria-label');
    if (aria) return trimText(aria);
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const label = labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.innerText || '').join(' ');
      if (label.trim()) return trimText(label);
    }
    if (el.id) {
      const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (label?.innerText) return trimText(label.innerText);
    }
    if (el.placeholder) return trimText(el.placeholder);
    if (el.value && ['BUTTON', 'INPUT'].includes(el.tagName)) return trimText(el.value);
    return trimText(el.innerText || el.textContent || '');
  }

  function serializeElement(el, includeHtml = false) {
    if (!el) return null;
    const ref = registerElement(el);
    return serializeElementNoRegister(el, ref, includeHtml);
  }

  function serializeElementNoRegister(el, ref, includeHtml = false) {
    const rect = el.getBoundingClientRect();
    const attrs = {};
    for (const attr of el.attributes || []) {
      if (['id', 'class', 'name', 'type', 'role', 'aria-label', 'placeholder', 'href', 'title', 'value'].includes(attr.name)) {
        attrs[attr.name] = attr.value;
      }
    }
    const obstruction = elementObstruction(el);
    const depthCtx = getElementDepthContext(el);
    const item = {
      ref: ref,
      tag: el.tagName.toLowerCase(),
      role: getRole(el) || undefined,
      text: elementLabel(el),
      value: el.value,
      selector: generateSelector(el),
      disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
      visible: isVisible(el),
      clickable: isClickable(el),
      covered: obstruction.covered,
      coveredBy: obstruction.covered ? {
        tag: obstruction.topTag,
        text: obstruction.topText,
        selector: obstruction.topSelector,
      } : undefined,
      inViewport: isInViewport(el),
      shadowHost: isShadowHost(el),
      insideShadowDom: depthCtx.insideShadow,
      insideIframe: depthCtx.insideIframe,
      attributes: attrs,
      rect: {
        x: Math.round(rect.x + window.scrollX),
        y: Math.round(rect.y + window.scrollY),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    };
    if (includeHtml) item.html = el.outerHTML;
    return item;
  }

  function resolveElementTarget(selectorOrRef, snapshotId) {
    if (!selectorOrRef || typeof selectorOrRef !== 'string') {
      throw new Error('请提供 selector 或 @e 引用');
    }
    if (/^@e\d+$/.test(selectorOrRef)) {
      const el = elementRegistry.get(selectorOrRef);
      if (el && el.isConnected) return el;
      // ref失效，尝试用记录的selector回退查找
      const fallbackSelector = refSelectors.get(selectorOrRef);
      if (fallbackSelector) {
        const found = document.querySelector(fallbackSelector);
        if (found && found.isConnected) {
          elementRegistry.set(selectorOrRef, found);
          return found;
        }
      }
      if (!el) throw new Error(`元素引用已失效或不存在: ${selectorOrRef}，请重新 snapshot`);
      elementRegistry.delete(selectorOrRef);
      snapshotRects.delete(selectorOrRef);
      refSelectors.delete(selectorOrRef);
      throw new Error(`元素引用已从页面移除: ${selectorOrRef}，请重新 snapshot`);
    }
    const el = document.querySelector(selectorOrRef);
    if (!el) throw new Error(`未找到元素: ${selectorOrRef}`);
    return el;
  }

  function validateRefStability(ref, tolerance = 50) {
    const el = elementRegistry.get(ref);
    if (!el || !el.isConnected) return { stable: false, reason: 'element_detached' };
    const snapshotRect = snapshotRects.get(ref);
    if (!snapshotRect) return { stable: true }; // 非 snapshot 注册的 ref，跳过校验
    const currentRect = el.getBoundingClientRect();
    const currentX = currentRect.x + window.scrollX;
    const currentY = currentRect.y + window.scrollY;
    const dx = Math.abs(currentX - snapshotRect.x);
    const dy = Math.abs(currentY - snapshotRect.y);
    if (dx > tolerance || dy > tolerance) {
      return { stable: false, reason: 'element_moved', dx: Math.round(dx), dy: Math.round(dy) };
    }
    return { stable: true };
  }

  function nextFrame() {
    return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }

  function collectSnapshotElements() {
    // 不重置 registry！保持元素编号在多次 snapshot 间稳定不变
    // 同一 DOM 元素永远对应同一个 @eN 编号（registerElement 已做幂等处理）
    const elements = [];

    function scan(root) {
      if (!root) return;
      const all = Array.from(root.querySelectorAll('*'));
      for (const el of all) {
        if (SKIPPED_TAGS.has(el.tagName)) continue;
        if (!isVisible(el)) continue;

        // 递归扫描 shadow DOM（Web Components 内部元素）
        if (el.shadowRoot) {
          scan(el.shadowRoot);
        }

        if (!isInteractive(el)) continue;

        const serialized = serializeElement(el);
        if (serialized?.ref) elements.push(serialized);
        if (elements.length >= 350) return;
      }
    }

    scan(document.body);

    // 尝试扫描同域 iframe（跨域 iframe 会抛出安全错误，直接忽略）
    try {
      const iframes = Array.from(document.querySelectorAll('iframe'));
      for (const iframe of iframes) {
        if (elements.length >= 350) break;
        try {
          const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
          if (iframeDoc && iframeDoc.body) scan(iframeDoc.body);
        } catch (_) {
          // 跨域 iframe 无法访问，忽略
        }
      }
    } catch (_) { /* ignore */ }

    // 清理已脱离 DOM 的旧引用（页面导航/元素被移除后）
    for (const [ref, el] of elementRegistry) {
      if (!el.isConnected) {
        elementRegistry.delete(ref);
        elementRefs.delete(el);
        refSelectors.delete(ref);
        snapshotRects.delete(ref);
      }
    }

    // 递增快照代际
    currentSnapshotId += 1;
    return elements;
  }

  // 稳定的语义属性键，用于传给 LLM 做锚点定位
  const SEMANTIC_ATTRS = ['id', 'aria-label', 'name', 'data-testid', 'placeholder'];

  function buildTree(elements) {
    return elements.map((el) => {
      const parts = [el.ref, el.tag];
      if (el.role) parts.push(`role=${el.role}`);
      if (el.text) parts.push(`"${el.text}"`);
      if (el.attributes?.type) parts.push(`type=${el.attributes.type}`);
      // 语义属性锚点: 仅输出稳定可定位的属性, 跳过空值
      for (const key of SEMANTIC_ATTRS) {
        const val = el.attributes?.[key];
        if (val && String(val).trim()) {
          const short = String(val).trim().slice(0, 80);
          parts.push(`${key}="${short}"`);
        }
      }
      if (el.disabled) parts.push('disabled');
      return parts.join(' ');
    }).join('\n');
  }

  // ═══════════════════════════════════════════════
  // 语义锚点查找: 不依赖 @e 编号, 按 text/id/aria-label 等属性在
  // 当前 DOM 中查找最佳匹配元素, 解决 SPA 弹窗/广告导致 @e 漂移问题
  // ═══════════════════════════════════════════════

  function findElementBySemanticAnchor(params) {
    const criteria = {};
    if (params.text) criteria.text = normalizeMatchText(params.text);
    if (params.id) criteria.id = String(params.id).trim();
    if (params.ariaLabel) criteria.ariaLabel = normalizeMatchText(params.ariaLabel);
    if (params.name) criteria.name = String(params.name).trim();
    if (params.testid) criteria.testid = String(params.testid).trim();
    if (params.placeholder) criteria.placeholder = normalizeMatchText(params.placeholder);
    if (params.tag) criteria.tag = String(params.tag).toLowerCase();

    if (!Object.keys(criteria).length) {
      throw new Error('语义查找需要提供 text / id / ariaLabel / name / testid / placeholder / tag 中至少一个');
    }

    const candidates = [];
    const all = Array.from(document.querySelectorAll('*'));
    for (const el of all) {
      if (SKIPPED_TAGS.has(el.tagName)) continue;
      if (!isVisible(el)) continue;
      if (!isInteractive(el)) continue;

      let score = 0;
      const elId = (el.id || '').trim();
      const elAriaLabel = normalizeMatchText(el.getAttribute('aria-label') || '');
      const elName = (el.getAttribute('name') || '').trim();
      const elTestId = (el.dataset?.testid || el.getAttribute('data-testid') || '').trim();
      const elPlaceholder = normalizeMatchText(el.getAttribute('placeholder') || '');
      const elText = normalizeMatchText(elementLabel(el));
      const elTag = el.tagName.toLowerCase();

      if (criteria.id) {
        score += elId === criteria.id ? 100 : (elId.includes(criteria.id) ? 50 : 0);
      }
      if (criteria.ariaLabel) {
        score += elAriaLabel === criteria.ariaLabel ? 80 : (elAriaLabel.includes(criteria.ariaLabel) ? 40 : 0);
      }
      if (criteria.name) {
        score += elName === criteria.name ? 80 : (elName.includes(criteria.name) ? 40 : 0);
      }
      if (criteria.testid) {
        score += elTestId === criteria.testid ? 80 : (elTestId.includes(criteria.testid) ? 40 : 0);
      }
      if (criteria.placeholder) {
        score += elPlaceholder === criteria.placeholder ? 60 : (elPlaceholder.includes(criteria.placeholder) ? 30 : 0);
      }
      if (criteria.text) {
        score += elText === criteria.text ? 70 : (elText.includes(criteria.text) ? 35 : 0);
      }
      if (criteria.tag) {
        score += elTag === criteria.tag ? 20 : 0;
      }

      // 被遮挡或禁用则大幅扣分
      if (el.disabled || el.getAttribute('aria-disabled') === 'true') score -= 100;
      const obstruction = elementObstruction(el);
      if (obstruction.covered) score -= 30;

      if (score > 0) candidates.push({ el, score });
    }

    if (!candidates.length) {
      throw new Error(`语义查找未找到匹配: ${JSON.stringify(params)}`);
    }

    candidates.sort((a, b) => b.score - a.score);
    return candidates[0].el;
  }

  function setNativeValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor?.set) descriptor.set.call(el, value);
    else el.value = value;
  }

  function selectElementContents(el) {
    const range = document.createRange();
    range.selectNodeContents(el);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }

  function fillContentEditable(el, text) {
    el.focus?.();
    selectElementContents(el);
    let inserted = false;
    try {
      el.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, cancelable: true, inputType: 'insertText', data: text }));
      inserted = document.execCommand?.('insertText', false, text) === true;
    } catch (_) {
      inserted = false;
    }
    if (!inserted) {
      el.textContent = text;
      el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
    }
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return { mode: 'contenteditable', inserted };
  }

  function fillElement(el, value) {
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') {
      throw new Error('元素已禁用，无法输入');
    }
    const text = String(value ?? '');
    // 检查当前值是否已经是目标文本，防止 LLM 重复 fill 陷入死循环
    const currentValue = (el.value ?? '').trim();
    const currentText = (el.textContent ?? '').trim();
    if (currentValue === text || currentText === text) {
      return {
        input: true,
        tag: el.tagName.toLowerCase(),
        mode: 'already_set',
        text: elementLabel(el),
        value: text,
        valueLength: text.length,
        alreadySet: true,
        message: `输入框已包含目标文本 "${text.slice(0, 50)}"，无需重复填写`,
      };
    }
    el.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
    el.focus?.();
    let mode = 'value';
    let inserted = true;
    if (el.isContentEditable) {
      const result = fillContentEditable(el, text);
      mode = result.mode;
      inserted = result.inserted;
    } else if (el.tagName === 'SELECT') {
      setNativeValue(el, text);
    } else if ('value' in el) {
      setNativeValue(el, text);
    } else {
      el.value = text;
      mode = 'fallback';
    }
    if (mode !== 'contenteditable') {
      el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
    return { input: true, tag: el.tagName.toLowerCase(), mode, inserted, text: elementLabel(el), value: text, valueLength: text.length };
  }

  function clickResult(el, extra = {}) {
    return {
      clicked: true,
      ref: elementRefs.get(el),
      tag: el.tagName.toLowerCase(),
      text: elementLabel(el),
      selector: generateSelector(el),
      ...extra
    };
  }

  function getElementCenter(el) {
    const rect = el.getBoundingClientRect();
    return {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
      rect,
    };
  }

  function elementObstruction(el) {
    const { x, y } = getElementCenter(el);
    const top = document.elementFromPoint(x, y);
    if (!top) return { covered: true, topTag: null, topText: '', x, y };
    const covered = top !== el && !el.contains(top) && !top.contains(el);
    return {
      covered,
      topTag: top.tagName?.toLowerCase?.() || '',
      topText: trimText(top.innerText || top.textContent || '', 80),
      topSelector: top instanceof Element ? generateSelector(top) : '',
      x,
      y,
    };
  }

  function elementSearchText(el) {
    const attrs = ['aria-label', 'title', 'placeholder', 'value', 'name', 'id', 'class', 'role'];
    const parts = [elementLabel(el), el.innerText, el.textContent];
    for (const attr of attrs) parts.push(el.getAttribute?.(attr));
    return parts.filter(Boolean).join(' ');
  }

  function scoreClickCandidate(el, query) {
    const queryText = normalizeMatchText(query);
    const haystack = normalizeMatchText(elementSearchText(el));
    let score = 0;
    if (!queryText) score += isInteractive(el) ? 20 : 0;
    if (queryText && haystack === queryText) score += 120;
    else if (queryText && haystack.includes(queryText)) score += 90;
    else if (queryText) {
      for (const token of queryText.split(/[，,;；|/]+/).filter(Boolean)) {
        if (token && haystack.includes(token)) score += 25;
      }
    }
    if (INTERACTIVE_TAGS.has(el.tagName)) score += 25;
    if (INTERACTIVE_ROLES.has(getRole(el))) score += 22;
    if (hasClickHandler(el)) score += 18;
    if (isVisible(el)) score += 20;
    const rect = el.getBoundingClientRect();
    if (rect.width >= 8 && rect.height >= 8) score += 10;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') score -= 100;
    const obstruction = elementObstruction(el);
    if (obstruction.covered) score -= 18;
    return { score, obstruction };
  }

  function collectClickCandidates(query, limit = 20) {
    resetElementRegistry();
    const seen = new Set();
    const raw = [];
    const all = Array.from(document.body ? document.body.querySelectorAll('*') : []);
    for (const el of all) {
      if (SKIPPED_TAGS.has(el.tagName)) continue;
      if (!isVisible(el)) continue;
      const text = normalizeMatchText(elementSearchText(el));
      const queryText = normalizeMatchText(query);
      if (!isInteractive(el) && (!queryText || !text.includes(queryText))) continue;
      const target = getClickableAncestor(el);
      if (!target || seen.has(target)) continue;
      seen.add(target);
      raw.push(target);
      if (raw.length >= 800) break;
    }
    const candidates = raw.map((el) => {
      const { score, obstruction } = scoreClickCandidate(el, query);
      const rect = el.getBoundingClientRect();
      return {
        element: el,
        score,
        ref: registerElement(el),
        selector: generateSelector(el),
        tag: el.tagName.toLowerCase(),
        role: getRole(el) || undefined,
        text: elementLabel(el),
        visible: isVisible(el),
        disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
        rect: {
          x: Math.round(rect.left + window.scrollX),
          y: Math.round(rect.top + window.scrollY),
          clientX: Math.round(rect.left),
          clientY: Math.round(rect.top),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        },
        obstruction,
      };
    }).filter((item) => item.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, Math.max(1, Math.min(Number(limit) || 20, 80)));
    return candidates;
  }

  function serializeClickCandidate(candidate) {
    const { element, ...rest } = candidate;
    return rest;
  }

  async function targetedClick(query, limit = 20) {
    const candidates = collectClickCandidates(query, limit);
    if (!candidates.length) throw new Error(`未找到匹配点击目标: ${query || '(空 query)'}`);
    const best = candidates[0];
    const bestElement = best.element;

    // 如果元素已在视口内，直接点击（避免第二次扫描耗时导致下拉菜单消失）
    if (isInViewport(bestElement)) {
      try {
        const click = await forceClickElement(bestElement);
        return {
          clicked: true,
          query,
          target: serializeClickCandidate(best),
          candidates: candidates.slice(0, 8).map(serializeClickCandidate),
          click,
        };
      } catch (_) {
        // forceClickElement 失败时 fall through 到二次扫描逻辑
      }
    }

    bestElement.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
    await nextFrame();
    const refreshed = collectClickCandidates(query, limit);
    // 用DOM元素直接比对，避免ref漂移到其他元素
    const target = (bestElement.isConnected && refreshed.find((item) => item.element === bestElement))
                || refreshed[0]
                || candidates[0];
    let click;
    try {
      click = await forceClickElement(target.element);
    } catch (forceError) {
      const center = getElementCenter(target.element);
      click = coordinateClick(center.x, center.y);
      click.strategy = 'coordinate_fallback_after_force_click';
      click.forceClickError = forceError.message;
    }
    return {
      clicked: true,
      query,
      target: serializeClickCandidate(target),
      candidates: refreshed.slice(0, 8).map(serializeClickCandidate),
      click,
    };
  }

  function dispatchPointerClick(el) {
    const rect = el.getBoundingClientRect();
    const clientX = rect.left + rect.width / 2;
    const clientY = rect.top + rect.height / 2;
    const commonOpts = { bubbles: true, cancelable: true, clientX, clientY, view: window, detail: 1 };
    el.dispatchEvent(new PointerEvent('pointerover', { ...commonOpts, pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0 }));
    el.dispatchEvent(new PointerEvent('pointerenter', { ...commonOpts, pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0 }));
    el.dispatchEvent(new MouseEvent('mouseover', { ...commonOpts, buttons: 0 }));
    el.dispatchEvent(new MouseEvent('mouseenter', { ...commonOpts, buttons: 0 }));
    el.dispatchEvent(new PointerEvent('pointerdown', { ...commonOpts, pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 1 }));
    el.dispatchEvent(new MouseEvent('mousedown', { ...commonOpts, button: 0, buttons: 1 }));
    el.dispatchEvent(new PointerEvent('pointerup', { ...commonOpts, pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0 }));
    el.dispatchEvent(new MouseEvent('mouseup', { ...commonOpts, button: 0, buttons: 0 }));
    el.dispatchEvent(new MouseEvent('click', { ...commonOpts, button: 0, buttons: 0 }));
    return { clientX, clientY };
  }

  async function standardClickElement(el) {
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') throw new Error('元素已禁用，无法点击');
    el.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
    await nextFrame(); // 等浏览器完成滚动和重排
    el.focus?.();
    const urlBefore = location.href;
    el.click();
    // 等待异步导航传播（SPA路由、pushState等），再检查URL是否变化
    await new Promise(r => setTimeout(r, 150));
    const urlAfter = location.href;
    return clickResult(el, {
      strategy: 'element.click',
      urlBefore,
      urlAfter,
      navigationDetected: urlBefore !== urlAfter,
    });
  }

  async function forceClickElement(el) {
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') throw new Error('元素已禁用，无法点击');
    const attempts = [];
    el.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
    await nextFrame(); // 等浏览器完成滚动和重排
    el.focus?.();
    try {
      el.click();
      attempts.push({ strategy: 'element.click', success: true });
    } catch (e) {
      attempts.push({ strategy: 'element.click', success: false, error: e.message });
    }
    try {
      const point = dispatchPointerClick(el);
      attempts.push({ strategy: 'dispatch_pointer_mouse_events', success: true, ...point });
    } catch (e) {
      attempts.push({ strategy: 'dispatch_pointer_mouse_events', success: false, error: e.message });
    }
    let mainWorld = null;
    try {
      mainWorld = await injectEvaluate(`
        const selector = ${JSON.stringify(generateSelector(el))};
        const el = document.querySelector(selector);
        if (!el) throw new Error('main world selector not found: ' + selector);
        el.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
        if (typeof el.focus === 'function') el.focus();
        el.click();
        return { clicked: true, strategy: 'main_world_element_click', selector, tag: el.tagName.toLowerCase(), text: (el.innerText || el.textContent || '').trim().slice(0, 160) };
      `);
      attempts.push({ strategy: 'main_world_element_click', success: true });
    } catch (e) {
      attempts.push({ strategy: 'main_world_element_click', success: false, error: e.message });
    }
    if (!attempts.some((attempt) => attempt.success)) {
      const obstruction = elementObstruction(el);
      let reason = attempts.map((attempt) => `${attempt.strategy}: ${attempt.error || 'unknown'}`).join('; ');
      if (obstruction.covered) {
        reason += `。注意：元素中心被其他元素遮挡，遮挡元素为 <${obstruction.topTag}> (${obstruction.topText})，selector=${obstruction.topSelector || 'none'}`;
      }
      if (!isInViewport(el)) {
        reason += '。注意：元素当前不在可视区域内，建议先 scroll_to';
      }
      if (getElementDepthContext(el).insideShadow) {
        reason += '。注意：元素位于 Shadow DOM 内，普通点击可能失效，可尝试 cdp_click 或 evaluate';
      }
      if (getElementDepthContext(el).insideIframe) {
        reason += '。注意：元素位于 iframe 内，请确认是否跨域，可尝试 cdp_click';
      }
      throw new Error('所有强制点击策略均失败: ' + reason);
    }
    const ref = elementRefs.get(el);
    const stability = ref ? validateRefStability(ref) : { stable: true };
    const urlBefore = location.href;
    const result = clickResult(el, {
      strategy: 'force_click',
      attempts,
      mainWorld,
      stability,
      urlBefore,
    });
    // 等待异步导航传播，再检测URL变化
    await new Promise(r => setTimeout(r, 150));
    const urlAfter = location.href;
    result.urlAfter = urlAfter;
    result.navigationDetected = urlBefore !== urlAfter;
    return result;
  }

  function coordinateClick(clientX, clientY) {
    if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) throw new Error('click_xy 需要有效的 x/y 坐标');
    const el = document.elementFromPoint(clientX, clientY);
    if (!el) throw new Error(`坐标 (${clientX}, ${clientY}) 未命中任何元素`);
    dispatchPointerClick(el);
    return { clicked: true, x: clientX, y: clientY, tag: el.tagName.toLowerCase(), text: elementLabel(el), selector: generateSelector(el), ref: elementRefs.get(el) };
  }

  function safeSerialize(value) {
    if (value instanceof Element) return serializeElement(value);
    try {
      JSON.stringify(value);
      return value;
    } catch (e) {
      return String(value);
    }
  }

  function buildExecutableScript(script) {
    const source = String(script || '').trim();
    if (!source) return 'return undefined;';
    if (/\breturn\b|;|\n/.test(source)) return source;
    return `return (${source});`;
  }

  async function runScript(script) {
    const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
    const fn = new AsyncFunction(`return (async () => { ${buildExecutableScript(script)} })();`);
    return safeSerialize(await fn());
  }

  async function injectEvaluate(script) {
    return new Promise((resolve, reject) => {
      const id = 'sigma-inject-' + Date.now() + '-' + Math.random().toString(36).slice(2);
      const executableSource = buildExecutableScript(script);
      let settled = false;
      const cleanup = () => {
        window.removeEventListener('message', listener);
        clearTimeout(timer);
      };
      const finish = (fn, value) => {
        if (settled) return;
        settled = true;
        cleanup();
        fn(value);
      };
      const listener = (e) => {
        if (e.source !== window || e.data?.source !== 'sigma-extension' || e.data?.id !== id) return;
        if (e.data.success) finish(resolve, e.data.result);
        else finish(reject, new Error(e.data.error || 'inject_evaluate failed'));
      };
      const timer = setTimeout(() => finish(reject, new Error('inject_evaluate timeout')), 10000);
      window.addEventListener('message', listener);
      const s = document.createElement('script');
      s.textContent = `
        (async function() {
          try {
            const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
            const fn = new AsyncFunction(${JSON.stringify(`return (async () => { ${executableSource} })();`)});
            const result = await fn();
            window.postMessage({ source: 'sigma-extension', id: '${id}', success: true, result }, '*');
          } catch (err) {
            window.postMessage({ source: 'sigma-extension', id: '${id}', success: false, error: err && (err.stack || err.message) || String(err) }, '*');
          }
        })();
      `;
      document.documentElement.appendChild(s);
      s.remove();
    }).then(safeSerialize);
  }

  const handlers = {
    ping: () => ({ pong: true }),

    snapshot: async () => {
      _logInfo('snapshot START');
      const elements = collectSnapshotElements();
      const result = {
        source: 'dom',
        url: location.href,
        title: document.title,
        text: trimText(document.body ? document.body.innerText : '', 2000),
        tree: buildTree(elements),
        elements,
        refCount: elements.length,
        snapshotId: currentSnapshotId,
      };
      // 附带页面截图（低质量JPEG），让LLM看到当前页面视觉状态
      try {
        const screenshot = await new Promise((resolve) => {
          chrome.runtime.sendMessage({ type: 'request_screenshot', format: 'jpeg', quality: 35 }, (resp) => {
            resolve(resp?.screenshot || '');
          });
        });
        if (screenshot) {
          result.screenshot = screenshot;
          result.screenshotNote = '低质量JPEG截图，用于视觉参考';
        }
      } catch (_) { /* 截图失败不影响主流程 */ }
      _logInfo('snapshot DONE', { refCount: elements.length, snapshotId: currentSnapshotId, hasScreenshot: !!result.screenshot, url: location.href.slice(0, 80) });
      return result;
    },

    get_page_html: () => ({ html: document.documentElement.outerHTML }),

    get_page_text: () => ({ text: document.body ? document.body.innerText : '' }),

    get_page_title: () => ({ title: document.title, url: location.href }),

    viewport: () => ({
      width: window.innerWidth,
      height: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio || 1,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      url: location.href,
      title: document.title
    }),

    query_selector: ({ selector }) => {
      return { element: serializeElement(resolveElementTarget(selector), true) };
    },

    // 语义锚点查找: 在当前 DOM 中按 text/id/aria-label 等属性实时匹配元素
    // 不依赖 @e 编号, 解决 SPA 弹窗/广告导致编号漂移问题
    // 参数: text / id / ariaLabel / name / testid / placeholder / tag (至少一个)
    find_element: (params) => {
      _logInfo('find_element START', params);
      const el = findElementBySemanticAnchor(params);
      const serialized = serializeElement(el);
      _logInfo('find_element DONE', { ref: serialized?.ref, text: serialized?.text, tag: serialized?.tag });
      return {
        found: true,
        element: serialized,
        hint: serialized?.ref
          ? `使用 ref "${serialized.ref}" 进行后续 click/fill 操作`
          : '未找到稳定引用，建议使用元素信息中的 selector 进行操作',
      };
    },

    // 语义点击: 按语义属性在当前 DOM 中找到元素并点击
    // 优先使用此命令替代 click + @e 编号的组合
    // 参数: text / id / ariaLabel / name / testid / placeholder / tag (至少一个)
    smart_click: async (params) => {
      _logInfo('smart_click START', params);
      const el = findElementBySemanticAnchor(params);
      const ref = elementRefs.get(el);
      const serialized = serializeElement(el);
      _logInfo('smart_click resolved', { ref: serialized?.ref, text: serialized?.text, tag: serialized?.tag });
      const result = await forceClickElement(el);
      _logAction('smart_click', params, result);
      return result;
    },

    query_selector_all: ({ selector }) => {
      const elements = Array.from(document.querySelectorAll(selector)).filter(isVisible).map((el) => serializeElement(el));
      return { elements, count: elements.length };
    },

    inspect_click_target: ({ query, limit }) => {
      const candidates = collectClickCandidates(query, limit).map(serializeClickCandidate);
      return { query: query || '', best: candidates[0] || null, candidates, count: candidates.length };
    },

    targeted_click: async ({ query, limit }) => {
      _logInfo('targeted_click START', { query, limit });
      const result = await targetedClick(query, limit);
      _logAction('targeted_click', { query, limit }, result);
      return result;
    },

    click: async ({ selector, snapshotId }) => {
      _logInfo('click START', { selector, snapshotId });
      const el = resolveElementTarget(selector, snapshotId);
      const ref = elementRefs.get(el);
      if (ref) {
        const stability = validateRefStability(ref);
        _logInfo('click stability check', { ref, stability });
        if (!stability.stable) {
          _logWarn('click STALE REF', { ref, stability });
          return {
            clicked: false,
            reason: stability.reason,
            message: stability.reason === 'element_moved'
              ? `元素位置已漂移（Δx=${stability.dx}px, Δy=${stability.dy}px），请重新 snapshot 后再点击`
              : `元素已脱离文档，请重新 snapshot`,
            needsSnapshot: true,
          };
        }
      }
      const result = await standardClickElement(el);
      _logAction('click', { selector, snapshotId }, result);
      return result;
    },

    force_click: async ({ selector, snapshotId }) => {
      _logInfo('force_click START', { selector, snapshotId });
      const el = resolveElementTarget(selector, snapshotId);
      const ref = elementRefs.get(el);
      if (ref) {
        const stability = validateRefStability(ref);
        _logInfo('force_click stability check', { ref, stability });
        if (!stability.stable) {
          _logWarn('force_click STALE REF', { ref, stability });
          return {
            clicked: false,
            reason: stability.reason,
            message: stability.reason === 'element_moved'
              ? `元素位置已漂移（Δx=${stability.dx}px, Δy=${stability.dy}px），请重新 snapshot 后再点击`
              : `元素已脱离文档，请重新 snapshot`,
            needsSnapshot: true,
          };
        }
      }
      const result = await forceClickElement(el);
      _logAction('force_click', { selector, snapshotId }, result);
      return result;
    },

    js_click: async ({ selector, snapshotId }) => {
      _logInfo('js_click START', { selector, snapshotId });
      const el = resolveElementTarget(selector, snapshotId);
      const ref = elementRefs.get(el);
      if (ref) {
        const stability = validateRefStability(ref);
        _logInfo('js_click stability check', { ref, stability });
        if (!stability.stable) {
          _logWarn('js_click STALE REF', { ref, stability });
          return {
            clicked: false,
            reason: stability.reason,
            message: stability.reason === 'element_moved'
              ? `元素位置已漂移（Δx=${stability.dx}px, Δy=${stability.dy}px），请重新 snapshot 后再点击`
              : `元素已脱离文档，请重新 snapshot`,
            needsSnapshot: true,
          };
        }
      }
      const result = await forceClickElement(el);
      _logAction('js_click', { selector, snapshotId }, result);
      return result;
    },

    click_xy: ({ x, y }) => {
      _logInfo('click_xy START', { x, y });
      const result = coordinateClick(Number(x), Number(y));
      _logAction('click_xy', { x, y }, result);
      return result;
    },

    input: ({ selector, value }) => {
      _logInfo('input START', { selector, value: String(value).slice(0, 80) });
      const result = fillElement(resolveElementTarget(selector), value);
      _logAction('input', { selector }, result);
      return result;
    },

    fill: ({ selector, value }) => {
      _logInfo('fill START', { selector, value: String(value).slice(0, 80) });
      const result = fillElement(resolveElementTarget(selector), value);
      _logAction('fill', { selector }, result);
      return result;
    },

    scroll_to: ({ selector, x, y }) => {
      if (selector) {
        const el = resolveElementTarget(selector);
        el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
        return { scrolled: true, selector, ref: elementRefs.get(el) };
      }
      if (x !== undefined && y !== undefined) {
        window.scrollTo(Number(x), Number(y));
        return { scrolled: true, x: Number(x), y: Number(y) };
      }
      throw new Error('请提供 selector 或 x/y');
    },

    hover: ({ selector }) => {
      _logInfo('hover START', { selector });
      const el = resolveElementTarget(selector);
      if (el.disabled || el.getAttribute('aria-disabled') === 'true') throw new Error('元素已禁用，无法悬停');
      el.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
      const rect = el.getBoundingClientRect();
      const clientX = rect.left + rect.width / 2;
      const clientY = rect.top + rect.height / 2;
      el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true, cancelable: true, clientX, clientY }));
      el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, clientX, clientY, relatedTarget: el }));
      el.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, cancelable: true, clientX, clientY }));
      return { hovered: true, selector, ref: elementRefs.get(el), tag: el.tagName.toLowerCase(), text: elementLabel(el) };
    },

    keypress: ({ selector, key, code, ctrl, alt, shift, meta }) => {
      const keyValue = String(key || '');
      if (!keyValue) throw new Error('请提供 key 参数');
      let target = document.body;
      let ref = undefined;
      if (selector) {
        target = resolveElementTarget(selector);
        ref = elementRefs.get(target);
        target.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
        target.focus?.();
      }
      const opts = {
        bubbles: true,
        cancelable: true,
        key: keyValue,
        code: String(code || keyValue),
        ctrlKey: Boolean(ctrl),
        altKey: Boolean(alt),
        shiftKey: Boolean(shift),
        metaKey: Boolean(meta),
      };
      target.dispatchEvent(new KeyboardEvent('keydown', opts));
      if (keyValue.length === 1 && 'value' in target && !target.readOnly && !target.disabled) {
        const start = target.selectionStart ?? target.value.length;
        const end = target.selectionEnd ?? target.value.length;
        target.value = target.value.slice(0, start) + keyValue + target.value.slice(end);
        target.selectionStart = target.selectionEnd = start + 1;
        target.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: keyValue }));
      }
      target.dispatchEvent(new KeyboardEvent('keyup', opts));
      return { keypressed: true, key: keyValue, selector, ref, tag: target.tagName?.toLowerCase?.() };
    },

    select: ({ selector, value, index, text }) => {
      const el = resolveElementTarget(selector);
      if (el.tagName !== 'SELECT') throw new Error(`元素不是 SELECT: ${selector}`);
      let option = null;
      if (value !== undefined) {
        option = Array.from(el.options).find((o) => o.value === String(value));
      } else if (index !== undefined) {
        const idx = Number(index);
        if (idx >= 0 && idx < el.options.length) option = el.options[idx];
      } else if (text !== undefined) {
        const t = String(text).trim();
        option = Array.from(el.options).find((o) => (o.text || '').trim() === t);
      } else {
        throw new Error('请提供 value、index 或 text 中的一个');
      }
      if (!option) throw new Error(`未找到匹配选项: value=${value} index=${index} text=${text}`);
      setNativeValue(el, option.value);
      el.dispatchEvent(new Event('change', { bubbles: true }));
      el.dispatchEvent(new Event('input', { bubbles: true }));
      return { selected: true, value: option.value, text: option.text, index: option.index, selector, ref: elementRefs.get(el) };
    },

    evaluate: ({ script }) => runScript(script),

    inject_evaluate: ({ script }) => injectEvaluate(script),

    highlight: ({ selector, selectors, color = '#fbbf24' }) => {
      const inputs = Array.isArray(selectors) ? selectors : [selector].filter(Boolean);
      const targets = [];
      inputs.forEach((item) => {
        if (/^@e\d+$/.test(item || '')) targets.push(resolveElementTarget(item));
        else targets.push(...Array.from(document.querySelectorAll(item)));
      });
      targets.forEach((el, index) => {
        if (!el.dataset.sigmaOriginalOutline) el.dataset.sigmaOriginalOutline = el.style.outline || '';
        if (!el.dataset.sigmaOriginalBoxShadow) el.dataset.sigmaOriginalBoxShadow = el.style.boxShadow || '';
        el.style.outline = `3px solid ${color}`;
        el.style.boxShadow = `0 0 0 6px rgba(34, 197, 94, 0.25), ${el.dataset.sigmaOriginalBoxShadow || ''}`;
        el.dataset.sigmaHighlightIndex = String(index + 1);
      });
      return { highlighted: targets.length, selectors: inputs };
    },

    clear_highlight: ({ selector, selectors }) => {
      const inputs = Array.isArray(selectors) ? selectors : (selector ? [selector] : []);
      const targets = inputs.length
        ? inputs.flatMap((item) => /^@e\d+$/.test(item || '') ? [resolveElementTarget(item)] : Array.from(document.querySelectorAll(item)))
        : Array.from(document.querySelectorAll('[data-sigma-original-outline]'));
      targets.forEach((el) => {
        el.style.outline = el.dataset.sigmaOriginalOutline || '';
        el.style.boxShadow = el.dataset.sigmaOriginalBoxShadow || '';
        delete el.dataset.sigmaOriginalOutline;
        delete el.dataset.sigmaOriginalBoxShadow;
        delete el.dataset.sigmaHighlightIndex;
      });
      return { cleared: targets.length };
    },

    sigma_status: ({ state }) => {
      setSigmaUiState(state || 'disconnected');
      return { state: sigmaUiState };
    },

    inspect_all_elements: ({ maxElements = 200 }) => {
      const results = scanInteractiveElements(maxElements);
      drawInspectBadges(results);
      return {
        total: results.length,
        elements: results,
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight,
          scrollX: window.scrollX,
          scrollY: window.scrollY,
        }
      };
    },

    clear_inspect: () => {
      clearAllInspectOverlays();
      clearStepBadges();
      return { cleared: true };
    },

    start_recording: () => {
      startRecording();
      return { recording: true };
    },

    stop_recording: () => {
      clearAllInspectOverlays();
      clearStepBadges();
        stopRecording();
        return { stopped: true };
      },

    get_bridge_logs: ({ limit = 50 }) => ({
      logs: _bridgeLogs.slice(-Math.min(limit, MAX_BRIDGE_LOGS)),
      total: _bridgeLogs.length,
      url: location.href,
    }),
  };

  // ===== inspect_all_elements 浮层绘制 =====
  let inspectBadges = [];

  function scanInteractiveElements(maxElements = 200) {
    clearAllInspectOverlays();

    const all = document.querySelectorAll('*');
    const results = [];
    for (const el of all) {
      if (results.length >= maxElements) break;
      if (!isInteractive(el) || !isVisible(el)) continue;
      // 记录元素引用，后续按位置排序后重新编号
      results.push({ el, rect: el.getBoundingClientRect() });
    }

    results.sort((a, b) => {
      const ay = a.rect.y, by = b.rect.y;
      if (Math.abs(ay - by) > 20) return ay - by;
      return a.rect.x - b.rect.x;
    });

    // 重新注册，确保 @eN 与排序位置一致
    resetElementRegistry();
    const elements = [];
    results.forEach((item, i) => {
      const el = item.el;
      if (!el || !el.isConnected) return;
      const ref = '@e' + (elements.length + 1);
      // 直接注册映射，跳过 serializeElement 里的 registerElement
      elementRefs.set(el, ref);
      elementRegistry.set(ref, el);
      refSelectors.set(ref, generateSelector(el));  // 记录selector用于ref失效回退
      const serialized = serializeElementNoRegister(el, ref);
      if (serialized) elements.push(serialized);
    });

    return elements;
  }

  function clearAllInspectOverlays() {
    inspectBadges.forEach((b) => {
      try {
        if (b._sigmaParent) {
          const el = b._sigmaParent;
          el.style.outline = el.dataset.sigmaOriginalOutline || '';
          delete el.dataset.sigmaOriginalOutline;
          if (b._sigmaOrigPosition !== undefined) {
            el.style.position = b._sigmaOrigPosition;
          }
        }
        b.remove();
      } catch (e) {}
    });
    inspectBadges = [];
  }

  function drawInspectBadges(elements) {
    clearAllInspectOverlays();
    elements.forEach((item, i) => {
      const el = elementRegistry.get(item.ref);
      if (!el || !el.isConnected) return;

      const origPosition = el.style.position;
      if (!origPosition || origPosition === 'static') {
        el.style.position = 'relative';
      }

      const isAiMode = el.dataset.sigmaAiMode === '1';
      const outlineColor = isAiMode ? '#3b82f6' : '#fbbf24';

      if (!el.dataset.sigmaOriginalOutline) el.dataset.sigmaOriginalOutline = el.style.outline || '';
      el.style.outline = `2px dashed ${outlineColor}`;

      // 简单徽章：编号 + 点击行为由 panel 模式决定
      const badge = document.createElement('div');
      badge.className = 'sigma-inspect-badge';
      badge.textContent = isAiMode ? i + 1 + ' AI' : i + 1;
      badge.title = isAiMode ? 'AI输入区域 (点击普通元素切换)' : '可点击录制';
      badge.setAttribute('aria-hidden', 'true');
      Object.assign(badge.style, {
        position: 'absolute',
        top: '-18px',
        left: '-2px',
        padding: '1px 5px',
        background: outlineColor,
        color: '#000',
        fontSize: '11px',
        fontWeight: '700',
        fontFamily: 'monospace',
        lineHeight: '16px',
        borderRadius: '3px',
        zIndex: '2147483646',
        pointerEvents: 'auto',
        cursor: 'pointer',
        boxShadow: `0 0 0 1px ${outlineColor}`,
        whiteSpace: 'nowrap',
      });
      badge.addEventListener('click', (e) => {
        if (!recordingActive) return;
        e.stopPropagation();
        e.preventDefault();
        if (e.ctrlKey || e.metaKey) {
          toggleAiMode(el, item, origPosition);
        } else {
          recordStepBg('click', {
            ref: item.ref, tag: item.tag, text: item.text,
            selector: item.selector,
            description: `点击 ${item.text || item.tag}`,
          });
        }
      });
      badge.addEventListener('contextmenu', (e) => {
        if (!recordingActive) return;
        e.stopPropagation();
        e.preventDefault();
        toggleAiMode(el, item, origPosition);
      });
      el.appendChild(badge);
      badge._sigmaParent = el;
      badge._sigmaOrigPosition = origPosition;
      badge._sigmaItem = item;
      inspectBadges.push(badge);
    });
  }

  function toggleAiMode(el, item, origPosition) {
    el.dataset.sigmaAiMode = el.dataset.sigmaAiMode === '1' ? '0' : '1';
    updateSingleBadge(item, el, origPosition);
    if (el.dataset.sigmaAiMode === '1') {
      recordStepBg('fill_ai', {
        ref: item.ref, tag: item.tag, text: item.text,
        selector: item.selector,
        description: `AI 输入区域: ${item.text || item.tag}`,
      });
    }
  }

  function updateSingleBadge(item, el, origPosition) {
    const old = inspectBadges.find(b => b._sigmaParent === el);
    if (old) {
      try { old.remove(); } catch (e) {}
      inspectBadges = inspectBadges.filter(b => b !== old);
    }
    const isAiMode = el.dataset.sigmaAiMode === '1';
    const outlineColor = isAiMode ? '#3b82f6' : '#fbbf24';
    el.style.outline = `2px dashed ${outlineColor}`;

    const badge = document.createElement('div');
    badge.className = 'sigma-inspect-badge';
    badge.textContent = isAiMode ? item.ref.replace('@e', '') + ' AI' : item.ref.replace('@e', '');
    badge.title = isAiMode ? 'AI输入区域 (Ctrl+点击切换)' : '可点击录制 (Ctrl+点击切换AI模式)';
    Object.assign(badge.style, {
      position: 'absolute', top: '-18px', left: '-2px',
      padding: '1px 5px', background: outlineColor, color: '#000',
      fontSize: '11px', fontWeight: '700', fontFamily: 'monospace',
      lineHeight: '16px', borderRadius: '3px', zIndex: '2147483646',
      pointerEvents: 'auto', cursor: 'pointer',
      boxShadow: `0 0 0 1px ${outlineColor}`, whiteSpace: 'nowrap',
    });
    badge.addEventListener('click', (e) => {
      if (!recordingActive) return;
      e.stopPropagation(); e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        toggleAiMode(el, item, origPosition);
      } else {
        recordStepBg('click', {
          ref: item.ref, tag: item.tag, text: item.text,
          selector: item.selector,
          description: `点击 ${item.text || item.tag}`,
        });
      }
    });
    badge.addEventListener('contextmenu', (e) => {
      if (!recordingActive) return;
      e.stopPropagation(); e.preventDefault();
      toggleAiMode(el, item, origPosition);
    });
    el.appendChild(badge);
    badge._sigmaParent = el;
    badge._sigmaOrigPosition = origPosition;
    badge._sigmaItem = item;
    inspectBadges.push(badge);
  }

  // ===== Sigma 连接状态可视化 =====
  let sigmaUiState = 'disconnected';
  let sigmaFrame = null;
  let sigmaBadge = null;
  let sigmaStyle = null;

  function ensureSigmaStyles() {
    if (sigmaStyle) return;
    sigmaStyle = document.createElement('style');
    sigmaStyle.id = 'sigma-status-styles';
    sigmaStyle.textContent = `
      .sigma-status-frame {
        position: fixed !important;
        inset: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        box-sizing: border-box !important;
        border: 4px solid #22c55e !important;
        pointer-events: none !important;
        z-index: 2147483647 !important;
        margin: 0 !important;
        padding: 0 !important;
        background: transparent !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
      }
      .sigma-status-frame.sigma-working {
        border: 0 !important;
        box-shadow: inset 0 0 0 4px rgba(255,255,255,0.9) !important;
      }
      .sigma-status-frame.sigma-working::before {
        content: '' !important;
        position: fixed !important;
        inset: 0 !important;
        padding: 6px !important;
        box-sizing: border-box !important;
        background: linear-gradient(90deg, #ff004c, #ff8a00, #ffe600, #00d26a, #00a3ff, #8b5cf6, #ff004c) !important;
        background-size: 300% 100% !important;
        animation: sigma-marquee 0.7s linear infinite !important;
        -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0) !important;
        -webkit-mask-composite: xor !important;
        mask-composite: exclude !important;
      }
      @keyframes sigma-marquee {
        0% { background-position: 0% 50%; }
        100% { background-position: 300% 50%; }
      }
      .sigma-status-badge {
        position: fixed !important;
        top: 8px !important;
        right: 8px !important;
        background: #22c55e !important;
        color: #fff !important;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        font-size: 12px !important;
        font-weight: 700 !important;
        padding: 5px 11px !important;
        border-radius: 6px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25) !important;
        pointer-events: none !important;
        z-index: 2147483648 !important;
        white-space: nowrap !important;
        letter-spacing: 0.3px !important;
        line-height: 1.4 !important;
      }
      .sigma-status-badge.sigma-working {
        background: linear-gradient(90deg, #ff0000, #ff7f00, #ffff00, #00ff00, #0000ff, #8b00ff, #ff0000) !important;
        background-size: 300% 100% !important;
        animation: sigma-marquee 0.8s linear infinite !important;
        color: #000 !important;
        text-shadow: 0 0 2px rgba(255,255,255,0.8) !important;
      }
    `;
    (document.head || document.documentElement).appendChild(sigmaStyle);
  }

  function removeSigmaUi() {
    if (sigmaFrame) { sigmaFrame.remove(); sigmaFrame = null; }
    if (sigmaBadge) { sigmaBadge.remove(); sigmaBadge = null; }
    if (sigmaStyle) { sigmaStyle.remove(); sigmaStyle = null; }
    sigmaUiState = 'disconnected';
  }

  function setSigmaUiState(state) {
    console.log('[Sigma Content] 状态切换:', state);
    sigmaUiState = state;
    if (state === 'disconnected') {
      removeSigmaUi();
      return;
    }
    ensureSigmaStyles();
    if (!sigmaFrame) {
      sigmaFrame = document.createElement('div');
      sigmaFrame.className = 'sigma-status-frame';
      sigmaFrame.setAttribute('aria-hidden', 'true');
      (document.body || document.documentElement).appendChild(sigmaFrame);
    }
    if (!sigmaBadge) {
      sigmaBadge = document.createElement('div');
      sigmaBadge.className = 'sigma-status-badge';
      sigmaBadge.textContent = 'Sigma Ready';
      sigmaBadge.setAttribute('aria-hidden', 'true');
      (document.body || document.documentElement).appendChild(sigmaBadge);
    }
    const isWorking = state === 'working';
    sigmaFrame.classList.toggle('sigma-working', isWorking);
    sigmaBadge.classList.toggle('sigma-working', isWorking);
    sigmaBadge.textContent = isWorking ? 'Sigma AI' : 'Sigma Ready';
  }

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    const { action, params = {} } = request;
    const handler = handlers[action];

    if (!handler) {
      sendResponse({ success: false, error: `未知命令: ${action}` });
      return false;
    }

    try {
      const result = handler(params);
      Promise.resolve(result)
        .then((data) => sendResponse({ success: true, data }))
        .catch((err) => sendResponse({ success: false, error: err && (err.stack || err.message) || String(err) }));
    } catch (err) {
      sendResponse({ success: false, error: err && (err.stack || err.message) || String(err) });
    }

    return true;
  });

  // ===== 录制引擎：记录用户操作序列 =====
  let recordingActive = false;
  let inputDebounceTimer = null;
  let lastInputValue = {};
  let recordingStartUrl = '';

  // 页面加载时检查全局录制状态
  chrome.runtime.sendMessage({ type: 'get_recording_status' }, (response) => {
    if (response?.recording) {
      recordingActive = true;
      recordingStartUrl = location.href;
      // 重新扫描并显示高亮
      clearStepBadges();
      const elements = scanInteractiveElements(200);
      drawInspectBadges(elements);
      showRecordingIndicator();
      updateRecordingBadge(response.stepCount || 0);
      // 记录导航
      recordStepBg('navigate', {
        url: location.href,
        title: document.title,
        description: `导航到 ${document.title || location.href}`,
      });
    }
  });

  function startRecording() {
    recordingActive = true;
    lastInputValue = {};
    recordingStartUrl = location.href;

    // 扫描元素并显示编号选框
    const elements = scanInteractiveElements(200);
    drawInspectBadges(elements);

    // 记录起始导航
    recordStepBg('navigate', {
      url: location.href,
      title: document.title,
      description: `打开 ${document.title || location.href}`,
    });

    showRecordingIndicator();
    updateRecordingBadge(1);
  }

  function stopRecording() {
    recordingActive = false;
    flushPendingInput();
    hideRecordingIndicator();
  }

  function flushPendingInput() {
    if (inputDebounceTimer) {
      clearTimeout(inputDebounceTimer);
      inputDebounceTimer = null;
    }
  }

  function recordStepBg(action, data) {
    if (!recordingActive) return;
    chrome.runtime.sendMessage({
      type: 'record_step',
      step: { action, ...data, timestamp: Date.now() }
    }, (response) => {
      if (response?.ok && recordingActive) {
        // 更新徽章计数（通过查询 background）
        chrome.runtime.sendMessage({ type: 'get_recording_status' }, (res) => {
          if (res?.stepCount !== undefined) updateRecordingBadge(res.stepCount);
        });
      }
    });
  }

  function recordClick(e) {
    if (!recordingActive) return;
    const el = getClickableAncestor(e.target);
    if (!el) return;

    const serialized = serializeElement(el);
    if (!serialized) return;

    recordStepBg('click', {
      ref: serialized.ref,
      tag: serialized.tag,
      text: serialized.text,
      selector: serialized.selector,
      description: `点击 ${serialized.text || serialized.tag}`,
    });
  }

  function recordInput(e) {
    if (!recordingActive) return;
    const el = e.target;
    if (!el || !['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) return;

    flushPendingInput();
    inputDebounceTimer = setTimeout(() => {
      inputDebounceTimer = null;
      const value = el.value || '';
      const key = el.name || el.id || generateSelector(el);

      if (lastInputValue[key] === value && value.length > 0) return;
      lastInputValue[key] = value;

      const serialized = serializeElement(el);
      if (!serialized) return;

      recordStepBg('fill', {
        ref: serialized.ref,
        tag: serialized.tag,
        text: serialized.text,
        selector: serialized.selector,
        value: value,
        description: `在 ${serialized.text || serialized.tag} 输入 "${value}"`,
      });
    }, 800);
  }

  function recordChange(e) {
    if (!recordingActive) return;
    const el = e.target;
    if (el.tagName !== 'SELECT') return;

    flushPendingInput();
    const serialized = serializeElement(el);
    if (!serialized) return;

    const selectedOption = el.options[el.selectedIndex];
    recordStepBg('select', {
      ref: serialized.ref,
      tag: serialized.tag,
      text: serialized.text,
      selector: serialized.selector,
      value: el.value,
      optionText: selectedOption?.text || el.value,
      description: `选择 "${selectedOption?.text || el.value}"`,
    });
  }

  // 监听导航（SPA 路由变化）
  let lastRecordedUrl = location.href;
  function checkUrlChange() {
    if (!recordingActive) return;
    if (location.href !== lastRecordedUrl) {
      lastRecordedUrl = location.href;
      setTimeout(() => {
        recordStepBg('navigate', {
          url: location.href,
          title: document.title,
          description: `导航到 ${document.title || location.href}`,
        });
      }, 500);
    }
  }

  document.addEventListener('click', recordClick, true);
  document.addEventListener('input', recordInput, true);
  document.addEventListener('change', recordChange, true);
  setInterval(checkUrlChange, 1000);

  // ===== 录制状态指示器 =====
  let recordingIndicator = null;
  let recordingBadge = null;

  function showRecordingIndicator() {
    if (recordingIndicator) return;

    // 页面顶部红色录制条
    recordingIndicator = document.createElement('div');
    Object.assign(recordingIndicator.style, {
      position: 'fixed',
      top: '0',
      left: '0',
      right: '0',
      height: '4px',
      background: '#ef4444',
      zIndex: '2147483645',
      animation: 'sigma-recording-pulse 1s ease-in-out infinite',
    });
    recordingIndicator.setAttribute('aria-hidden', 'true');
    (document.body || document.documentElement).appendChild(recordingIndicator);

    // 右下角计数徽章
    recordingBadge = document.createElement('div');
    Object.assign(recordingBadge.style, {
      position: 'fixed',
      bottom: '16px',
      right: '16px',
      padding: '6px 14px',
      background: '#ef4444',
      color: '#fff',
      fontSize: '13px',
      fontWeight: '700',
      fontFamily: 'monospace',
      borderRadius: '8px',
      zIndex: '2147483645',
      boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
      pointerEvents: 'none',
    });
    recordingBadge.textContent = '● REC 1步';
    (document.body || document.documentElement).appendChild(recordingBadge);

    // 动画样式
    const style = document.createElement('style');
    style.textContent = '@keyframes sigma-recording-pulse{0%,100%{opacity:1}50%{opacity:0.4}}';
    document.head.appendChild(style);
  }

  function hideRecordingIndicator() {
    if (recordingIndicator) { recordingIndicator.remove(); recordingIndicator = null; }
    if (recordingBadge) { recordingBadge.remove(); recordingBadge = null; }
  }

  function updateRecordingBadge(count) {
    if (recordingBadge && count !== undefined) {
      recordingBadge.textContent = `● REC ${count}步`;
    }
  }

  // ===== 步骤编号浮层（蓝色，全局连续） =====
  let stepBadges = [];

  function drawStepBadge(ref, stepNum) {
    const el = elementRegistry.get(ref);
    if (!el || !el.isConnected) return;

    const badge = document.createElement('div');
    Object.assign(badge.style, {
      position: 'absolute',
      top: '-34px',
      left: '-2px',
      padding: '2px 6px',
      background: '#3b82f6',
      color: '#fff',
      fontSize: '11px',
      fontWeight: '700',
      fontFamily: 'monospace',
      lineHeight: '16px',
      borderRadius: '10px',
      zIndex: '2147483646',
      pointerEvents: 'none',
      boxShadow: '0 2px 8px rgba(59,130,246,0.5)',
      whiteSpace: 'nowrap',
    });
    badge.textContent = 'Step ' + stepNum;
    el.appendChild(badge);
    stepBadges.push(badge);
  }

  function clearStepBadges() {
    stepBadges.forEach((b) => { try { b.remove(); } catch (e) {} });
    stepBadges = [];
  }

  // 更新 recordStepBg：步骤记录成功后画步骤编号
  const _origRecordStepBg = recordStepBg;
  recordStepBg = function(action, data) {
    if (!recordingActive) return;
    chrome.runtime.sendMessage({
      type: 'record_step',
      step: { action, ...data, timestamp: Date.now() }
    }, (response) => {
      if (response?.ok && recordingActive) {
        chrome.runtime.sendMessage({ type: 'get_recording_status' }, (res) => {
          if (res?.stepCount !== undefined) {
            updateRecordingBadge(res.stepCount);
            // 画步骤编号
            if (data.ref) {
              drawStepBadge(data.ref, res.stepCount);
            }
          }
        });
      }
    });
  };

  console.log('[Sigma Content] 已注入:', location.href);
})();
