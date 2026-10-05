(() => {
  function textOf(el) {
    return String(el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 240);
  }

  function attrs(el) {
    const out = {};
    for (const name of [
      "id", "role", "name", "type", "href", "aria-label", "aria-labelledby", "aria-describedby",
      "data-testid", "data-test", "data-cy", "data-ui-forge", "data-ui-forge-id", "data-ui-forge-source"
    ]) {
      const value = el.getAttribute && el.getAttribute(name);
      if (value) out[name] = value;
    }
    return out;
  }

  function compactStyle(style) {
    const keys = [
      "display", "position", "color", "backgroundColor", "fontFamily", "fontSize", "fontWeight",
      "lineHeight", "letterSpacing", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
      "marginTop", "marginRight", "marginBottom", "marginLeft", "borderRadius", "borderTopWidth",
      "borderRightWidth", "borderBottomWidth", "borderLeftWidth", "boxShadow", "opacity", "gap",
      "alignItems", "justifyContent", "gridTemplateColumns", "flexDirection", "width", "height"
    ];
    const out = {};
    for (const key of keys) {
      const value = style[key];
      if (value && value !== "normal" && value !== "none" && value !== "0px") out[key] = value;
    }
    return out;
  }

  function fingerprint(el) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    const parents = [];
    let node = el.parentElement;
    for (let i = 0; node && i < 5; i += 1, node = node.parentElement) {
      parents.push({
        tag: node.tagName.toLowerCase(),
        id: node.id || "",
        classes: Array.from(node.classList || []).slice(0, 8),
        source: node.getAttribute?.("data-ui-forge-source") || "",
        text: textOf(node).slice(0, 100),
      });
    }
    return {
      tag: el.tagName.toLowerCase(),
      text: textOf(el),
      id: el.id || "",
      classes: Array.from(el.classList || []).slice(0, 20),
      attributes: attrs(el),
      ui_forge_id: el.getAttribute?.("data-ui-forge-id") || "",
      ui_forge_source: el.getAttribute?.("data-ui-forge-source") || "",
      dataset: {...el.dataset},
      rect: {
        x: Math.round(rect.x * 100) / 100,
        y: Math.round(rect.y * 100) / 100,
        width: Math.round(rect.width * 100) / 100,
        height: Math.round(rect.height * 100) / 100,
      },
      computedStyle: compactStyle(style),
      parents,
      viewport: {width: innerWidth, height: innerHeight, dpr: devicePixelRatio},
      url: location.href,
      title: document.title,
    };
  }

  const selector = window.__UI_FORGE_SELECTOR__;
  let target = selector ? document.querySelector(selector) : document.activeElement;
  if (!target || target === document.body || target === document.documentElement) {
    target = document.querySelector("[data-ui-forge-source], [data-testid], button, a, input, h1, h2") || document.body;
  }
  return fingerprint(target);
})()
