(() => {
  const KEY = '__UI_FORGE_ASSET_PREVIEW__';
  if (window[KEY]?.installed) return window[KEY];

  const state = { installed: true, node: null, beforeSrc: null, active: null };
  const SAFE_PREFIX = '/ui-forge-assets/';

  function probe(node) {
    if (!(node instanceof HTMLImageElement)) return null;
    const rect = node.getBoundingClientRect();
    return {
      tag: 'img',
      src: node.getAttribute('src') || '',
      current_src: node.currentSrc || '',
      alt: node.getAttribute('alt') || '',
      ui_forge_source: node.getAttribute('data-ui-forge-source') || '',
      ui_forge_id: node.getAttribute('data-ui-forge-id') || '',
      natural_width: node.naturalWidth,
      natural_height: node.naturalHeight,
      complete: node.complete,
      rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      url: location.href,
    };
  }

  function revert() {
    if (!(state.node instanceof HTMLImageElement) || state.active == null) {
      state.active = null;
      return { reverted: false };
    }
    if (state.beforeSrc == null) state.node.removeAttribute('src');
    else state.node.setAttribute('src', state.beforeSrc);
    const selection = probe(state.node);
    state.active = null;
    return { reverted: true, selection };
  }

  const api = {
    installed: true,
    select(selector) {
      if (state.active) revert();
      const node = document.querySelector(String(selector));
      if (!(node instanceof HTMLImageElement)) return { ok: false, error: 'selector must resolve to an <img>' };
      state.node = node;
      state.beforeSrc = node.hasAttribute('src') ? node.getAttribute('src') : null;
      return { ok: true, selection: probe(node) };
    },
    async preview(publicUrl) {
      if (!(state.node instanceof HTMLImageElement)) return { ok: false, error: 'no selected image' };
      const value = String(publicUrl || '');
      if (!value.startsWith(SAFE_PREFIX) || value.includes('..') || value.includes('\\')) return { ok: false, error: 'asset preview URL must stay under /ui-forge-assets/' };
      if (state.active) revert();
      state.beforeSrc = state.node.hasAttribute('src') ? state.node.getAttribute('src') : null;
      state.node.setAttribute('src', value);
      await new Promise((resolve) => {
        if (state.node.complete) { resolve(); return; }
        const done = () => { state.node.removeEventListener('load', done); state.node.removeEventListener('error', done); resolve(); };
        state.node.addEventListener('load', done, { once: true });
        state.node.addEventListener('error', done, { once: true });
        setTimeout(done, 5000);
      });
      const selection = probe(state.node);
      const decoded = selection.complete && selection.natural_width > 0 && selection.natural_height > 0;
      state.active = { public_url: value };
      return { ok: decoded, preview_applied: true, decoded, selection, error: decoded ? '' : 'image did not decode' };
    },
    revert,
    commitSpec(alt = null) {
      if (!state.active || !(state.node instanceof HTMLImageElement)) return { ok: false, error: 'no active asset preview' };
      const selection = probe(state.node);
      const source = selection.ui_forge_source || '';
      return {
        ok: Boolean(source && selection.natural_width > 0 && selection.natural_height > 0),
        source,
        public_url: state.active.public_url,
        alt: alt == null ? selection.alt : String(alt),
        selection,
        error: source ? '' : 'selected image has no exact data-ui-forge-source',
      };
    },
    getSelection() { return probe(state.node); },
  };

  window.UIForgeAssetPreview = api;
  window[KEY] = api;
  return api;
})();
