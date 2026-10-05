(() => {
  const KEY = "__UI_FORGE_VISUAL_BRIDGE__";
  if (window[KEY]?.installed) return window[KEY];

  const state = {
    installed: true,
    enabled: false,
    hovered: null,
    selected: null,
    selectedNode: null,
    selectedNodes: [],
    preview: null,
    batchPreview: null,
    overlay: null,
    label: null,
  };

  function cleanText(node) {
    return String(node?.innerText || node?.textContent || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 240);
  }

  function elementProbe(node) {
    if (!(node instanceof Element)) return null;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    const source = node.getAttribute("data-ui-forge-source") || "";
    const forgeId = node.getAttribute("data-ui-forge-id") || "";
    return {
      tag: node.tagName.toLowerCase(),
      text: cleanText(node),
      id: node.id || "",
      classes: Array.from(node.classList || []).slice(0, 24),
      testid: node.getAttribute("data-testid") || "",
      aria_label: node.getAttribute("aria-label") || "",
      ui_forge_source: source,
      ui_forge_id: forgeId,
      rect: {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        left: rect.left,
      },
      computed_style: {
        display: style.display,
        position: style.position,
        color: style.color,
        backgroundColor: style.backgroundColor,
        fontFamily: style.fontFamily,
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        lineHeight: style.lineHeight,
        letterSpacing: style.letterSpacing,
        padding: style.padding,
        margin: style.margin,
        gap: style.gap,
        border: style.border,
        borderRadius: style.borderRadius,
        boxShadow: style.boxShadow,
        width: style.width,
        height: style.height,
      },
      viewport: {
        width: innerWidth,
        height: innerHeight,
        dpr: devicePixelRatio,
        scrollX,
        scrollY,
      },
      url: location.href,
      title: document.title,
    };
  }

  function ensureOverlay() {
    if (state.overlay && state.label) return;
    const overlay = document.createElement("div");
    overlay.setAttribute("data-ui-forge-overlay", "true");
    Object.assign(overlay.style, {
      position: "fixed",
      zIndex: "2147483646",
      pointerEvents: "none",
      border: "2px solid #22c55e",
      background: "rgba(34,197,94,0.08)",
      boxSizing: "border-box",
      display: "none",
    });
    const label = document.createElement("div");
    label.setAttribute("data-ui-forge-overlay-label", "true");
    Object.assign(label.style, {
      position: "fixed",
      zIndex: "2147483647",
      pointerEvents: "none",
      background: "#111827",
      color: "#f9fafb",
      borderRadius: "4px",
      padding: "4px 6px",
      font: "11px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace",
      maxWidth: "480px",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
      display: "none",
    });
    document.documentElement.append(overlay, label);
    state.overlay = overlay;
    state.label = label;
  }

  function render(node, selected = false) {
    ensureOverlay();
    if (!(node instanceof Element)) {
      state.overlay.style.display = "none";
      state.label.style.display = "none";
      return;
    }
    const rect = node.getBoundingClientRect();
    Object.assign(state.overlay.style, {
      display: "block",
      left: `${Math.max(0, rect.left)}px`,
      top: `${Math.max(0, rect.top)}px`,
      width: `${Math.max(0, rect.width)}px`,
      height: `${Math.max(0, rect.height)}px`,
      borderColor: selected ? "#f59e0b" : "#22c55e",
      background: selected ? "rgba(245,158,11,0.10)" : "rgba(34,197,94,0.08)",
    });
    const source = node.getAttribute("data-ui-forge-source");
    const id = node.getAttribute("data-ui-forge-id");
    const labelText = source || id || `${node.tagName.toLowerCase()}${node.id ? `#${node.id}` : ""}`;
    state.label.textContent = `${selected ? "SELECTED" : "UI FORGE"} Â· ${labelText}`;
    Object.assign(state.label.style, {
      display: "block",
      left: `${Math.max(4, Math.min(innerWidth - 200, rect.left))}px`,
      top: `${Math.max(4, rect.top - 24)}px`,
    });
  }

  const SAFE_PREVIEW_ATTRIBUTES = new Set([
    "aria-label", "aria-description", "aria-live", "aria-current",
    "title", "placeholder", "alt", "role", "name", "type", "inputMode",
  ]);

  const SAFE_PREVIEW_INTERACTION_STATES = new Set(["hover", "focus", "focus-visible", "active", "disabled", "checked"]);

  const SAFE_PREVIEW_STYLE_PROPERTIES = new Set([
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "gap", "row-gap", "column-gap", "color", "background", "background-color", "opacity",
    "font-family", "font-size", "font-weight", "font-style", "line-height", "letter-spacing", "text-align",
    "border", "border-width", "border-style", "border-color", "border-radius", "box-shadow", "outline", "outline-offset",
    "width", "min-width", "max-width", "height", "min-height", "max-height",
    "display", "flex", "flex-direction", "flex-wrap", "align-items", "justify-content",
    "grid-template-columns", "grid-template-rows", "grid-auto-flow", "place-items",
    "position", "top", "right", "bottom", "left", "inset", "z-index", "overflow", "overflow-x", "overflow-y",
    "transform", "transform-origin", "transition", "cursor", "object-fit", "object-position",
  ]);

  function normalizePreviewMedia(raw) {
    if (raw == null || raw === "" || (Array.isArray(raw) && raw.length === 0)) return { ok: true, media_chain: [] };
    const items = Array.isArray(raw) ? raw : [raw];
    if (items.length > 4) return { ok: false, error: "media_chain is limited to 4 contexts" };
    const media_chain = [];
    for (const item of items) {
      const text = String(item || "").trim().replace(/\s+/g, " ");
      if (!text || text.length > 240 || /[{};]/.test(text)) return { ok: false, error: "media_chain contains unsafe or empty context" };
      media_chain.push(text);
    }
    return { ok: true, media_chain };
  }

  function validateStyleProperties(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { ok: false, error: "style_props.properties must be an object" };
    const entries = Object.entries(raw);
    if (!entries.length) return { ok: false, error: "style_props.properties cannot be empty" };
    if (entries.length > 20) return { ok: false, error: "style_props is limited to 20 declarations" };
    const properties = {};
    for (const [nameRaw, valueRaw] of entries) {
      const name = String(nameRaw).trim().toLowerCase();
      const value = String(valueRaw).trim();
      if (!SAFE_PREVIEW_STYLE_PROPERTIES.has(name)) return { ok: false, error: `CSS property is not preview-allowlisted: ${name || "<empty>"}` };
      if (!value) return { ok: false, error: `CSS value cannot be empty: ${name}` };
      if (/[;{}]/.test(value) || /url\s*\(/i.test(value)) return { ok: false, error: `CSS value requires the main coding path: ${name}` };
      properties[name] = value;
    }
    return { ok: true, properties };
  }

  function revertPreview() {
    const preview = state.preview;
    if (!preview || !(preview.node instanceof Element)) {
      state.preview = null;
      return { reverted: false };
    }
    const node = preview.node;
    if (preview.kind === "text") node.textContent = preview.beforeText;
    else if (preview.kind === "text_segment") preview.textNode.nodeValue = preview.beforeTextSegment;
    else if (preview.kind === "class") {
      if (preview.hadClass) node.setAttribute("class", preview.beforeClass);
      else node.removeAttribute("class");
    } else if (preview.kind === "attribute") {
      if (preview.hadAttribute) node.setAttribute(preview.attribute, preview.beforeAttribute);
      else node.removeAttribute(preview.attribute);
    } else if (preview.kind === "style") {
      if (preview.hadStyle) node.setAttribute("style", preview.beforeStyle);
      else node.removeAttribute("style");
    }
    state.preview = null;
    if (state.selectedNode === node) {
      state.selected = elementProbe(node);
      render(node, true);
    }
    return { reverted: true, selection: elementProbe(node) };
  }

  function previewOperation(operation) {
    const node = state.selectedNode || state.hovered;
    if (!(node instanceof Element)) return { ok: false, error: "no selected element" };
    if (!operation || typeof operation !== "object") return { ok: false, error: "operation must be an object" };
    if (state.preview) revertPreview();
    const type = String(operation.type || "");
    let preview;
    if (type === "set_text") {
      if (node.children.length !== 0) return { ok: false, error: "refusing preview set_text on nested element content" };
      const value = String(operation.value ?? "");
      preview = { node, kind: "text", beforeText: node.textContent };
      node.textContent = value;
    } else if (type === "set_text_segment") {
      const index = Number(operation.segment_index ?? 0);
      const textNodes = Array.from(node.childNodes).filter((child) => child.nodeType === Node.TEXT_NODE && String(child.nodeValue || "").trim().length > 0);
      if (!Number.isInteger(index) || index < 0 || index >= textNodes.length) return { ok: false, error: "refusing preview set_text_segment: segment_index does not identify a static text node" };
      const target = textNodes[index];
      const before = String(target.nodeValue || "");
      const trimmed = before.trim();
      if (operation.expected_text != null && trimmed !== String(operation.expected_text)) return { ok: false, error: "refusing preview set_text_segment: expected_text does not match rendered text" };
      const value = String(operation.value ?? "");
      const start = before.indexOf(trimmed);
      preview = { node, kind: "text_segment", textNode: target, beforeTextSegment: before };
      target.nodeValue = before.slice(0, start) + value + before.slice(start + trimmed.length);
      operation = { ...operation, segment_index: index, expected_text: trimmed, value };    } else if (type === "class_tokens") {
      preview = { node, kind: "class", hadClass: node.hasAttribute("class"), beforeClass: node.getAttribute("class") || "" };
      for (const token of Array.isArray(operation.remove) ? operation.remove : []) node.classList.remove(String(token));
      for (const token of Array.isArray(operation.add) ? operation.add : []) if (String(token)) node.classList.add(String(token));
    } else if (type === "replace_class") {
      preview = { node, kind: "class", hadClass: node.hasAttribute("class"), beforeClass: node.getAttribute("class") || "" };
      node.setAttribute("class", String(operation.value ?? ""));
    } else if (type === "set_attribute") {
      const name = String(operation.name || "");
      if (!SAFE_PREVIEW_ATTRIBUTES.has(name)) return { ok: false, error: `attribute ${name || "<empty>"} is not preview-allowlisted` };
      preview = {
        node, kind: "attribute", attribute: name,
        hadAttribute: node.hasAttribute(name), beforeAttribute: node.getAttribute(name) || "",
      };
      node.setAttribute(name, String(operation.value ?? ""));
    } else if (type === "style_props") {
      const checked = validateStyleProperties(operation.properties);
      if (!checked.ok) return checked;
      const requestedState = operation.state == null || operation.state === "" ? null : String(operation.state).trim().toLowerCase();
      if (requestedState && !SAFE_PREVIEW_INTERACTION_STATES.has(requestedState)) return { ok: false, error: `unsupported interaction state: ${requestedState}` };
      const media = normalizePreviewMedia(operation.media_chain ?? operation.media ?? null);
      if (!media.ok) return media;
      preview = { node, kind: "style", hadStyle: node.hasAttribute("style"), beforeStyle: node.getAttribute("style") || "" };
      for (const [name, value] of Object.entries(checked.properties)) node.style.setProperty(name, value);
      operation = { type: "style_props", properties: checked.properties, ...(requestedState ? { state: requestedState } : {}), ...(media.media_chain.length ? { media_chain: media.media_chain } : {}) };
    } else {
      return { ok: false, error: `unsupported preview operation: ${type || "<empty>"}` };
    }
    state.preview = { ...preview, operation: JSON.parse(JSON.stringify(operation)) };
    state.selected = elementProbe(node);
    render(node, true);
    const isStylePreview = state.preview.operation.type === "style_props";
    const styleRequest = isStylePreview ? {
      probe: state.selected,
      declarations: state.preview.operation.properties,
      ...(state.preview.operation.state ? { state: state.preview.operation.state } : {}),
      ...(state.preview.operation.media_chain ? { media_chain: state.preview.operation.media_chain } : {}),
    } : null;
    return {
      ok: true,
      preview_applied: true,
      selection: state.selected,
      source_edit: isStylePreview ? null : {
        source: state.selected.ui_forge_source || "",
        operation: state.preview.operation,
      },
      style_request: styleRequest,
      commit_ready: isStylePreview ? false : Boolean(state.selected.ui_forge_source),
      style_commit_ready: isStylePreview && Boolean(state.selected.id || state.selected.classes?.length),
    };
  }

  function validateBatchOperation(node, operation) {
    if (!(node instanceof Element)) return "selection is not an element";
    if (!operation || typeof operation !== "object") return "operation must be an object";
    const type = String(operation.type || "");
    if (type === "set_text") {
      if (node.children.length !== 0) return "refusing batch set_text on nested element content";
      return "";
    }
    if (type === "class_tokens" || type === "replace_class") return "";
    if (type === "set_attribute") {
      const name = String(operation.name || "");
      return SAFE_PREVIEW_ATTRIBUTES.has(name) ? "" : `attribute ${name || "<empty>"} is not preview-allowlisted`;
    }
    return `unsupported preview operation: ${type || "<empty>"}`;
  }

  function captureNodePreview(node, operation) {
    const type = String(operation.type || "");
    if (type === "set_text") {
      return { node, kind: "text", beforeText: node.textContent };
    }
    if (type === "class_tokens" || type === "replace_class") {
      return { node, kind: "class", hadClass: node.hasAttribute("class"), beforeClass: node.getAttribute("class") || "" };
    }
    const name = String(operation.name || "");
    return {
      node,
      kind: "attribute",
      attribute: name,
      hadAttribute: node.hasAttribute(name),
      beforeAttribute: node.getAttribute(name) || "",
    };
  }

  function applyOperationToNode(node, operation) {
    const type = String(operation.type || "");
    if (type === "set_text") {
      node.textContent = String(operation.value ?? "");
    } else if (type === "set_text_segment") {
      const index = Number(operation.segment_index ?? 0);
      const textNodes = Array.from(node.childNodes).filter((child) => child.nodeType === Node.TEXT_NODE && String(child.nodeValue || "").trim().length > 0);
      if (!Number.isInteger(index) || index < 0 || index >= textNodes.length) return { ok: false, error: "refusing preview set_text_segment: segment_index does not identify a static text node" };
      const target = textNodes[index];
      const before = String(target.nodeValue || "");
      const trimmed = before.trim();
      if (operation.expected_text != null && trimmed !== String(operation.expected_text)) return { ok: false, error: "refusing preview set_text_segment: expected_text does not match rendered text" };
      const value = String(operation.value ?? "");
      const start = before.indexOf(trimmed);
      preview = { node, kind: "text_segment", textNode: target, beforeTextSegment: before };
      target.nodeValue = before.slice(0, start) + value + before.slice(start + trimmed.length);
      operation = { ...operation, segment_index: index, expected_text: trimmed, value };    } else if (type === "class_tokens") {
      for (const token of Array.isArray(operation.remove) ? operation.remove : []) node.classList.remove(String(token));
      for (const token of Array.isArray(operation.add) ? operation.add : []) if (String(token)) node.classList.add(String(token));
    } else if (type === "replace_class") {
      node.setAttribute("class", String(operation.value ?? ""));
    } else if (type === "set_attribute") {
      node.setAttribute(String(operation.name || ""), String(operation.value ?? ""));
    }
  }

  function restoreNodePreview(preview) {
    const node = preview?.node;
    if (!(node instanceof Element)) return;
    if (preview.kind === "text") node.textContent = preview.beforeText;
    else if (preview.kind === "text_segment") preview.textNode.nodeValue = preview.beforeTextSegment;
    else if (preview.kind === "class") {
      if (preview.hadClass) node.setAttribute("class", preview.beforeClass);
      else node.removeAttribute("class");
    } else if (preview.kind === "attribute") {
      if (preview.hadAttribute) node.setAttribute(preview.attribute, preview.beforeAttribute);
      else node.removeAttribute(preview.attribute);
    }
  }

  function revertBatchPreview() {
    const batch = state.batchPreview;
    if (!batch) return { reverted: false };
    for (const preview of [...batch.previews].reverse()) restoreNodePreview(preview);
    state.batchPreview = null;
    const selections = state.selectedNodes.filter((node) => node instanceof Element).map(elementProbe);
    if (state.selectedNode instanceof Element) {
      state.selected = elementProbe(state.selectedNode);
      render(state.selectedNode, true);
    }
    return { reverted: true, selections };
  }

  function previewMany(operation) {
    if (state.preview) revertPreview();
    if (state.batchPreview) revertBatchPreview();
    const nodes = state.selectedNodes.length
      ? state.selectedNodes.filter((node) => node instanceof Element)
      : state.selectedNode instanceof Element ? [state.selectedNode] : [];
    if (!nodes.length) return { ok: false, error: "no selected elements" };

    const errors = nodes.map((node, index) => ({ index, error: validateBatchOperation(node, operation) })).filter((item) => item.error);
    if (errors.length) return { ok: false, error: "batch preview refused; at least one selection is unsafe", errors };

    const op = JSON.parse(JSON.stringify(operation));
    const previews = nodes.map((node) => captureNodePreview(node, op));
    for (const node of nodes) applyOperationToNode(node, op);
    state.batchPreview = { previews, operation: op };

    const selections = nodes.map(elementProbe);
    const sourceEdits = selections.map((selection) => ({
      source: selection.ui_forge_source || "",
      operation: op,
    }));
    const sources = sourceEdits.map((edit) => edit.source).filter(Boolean);
    const uniqueSources = new Set(sources);
    const commitReady = sources.length === nodes.length && uniqueSources.size === nodes.length;
    if (state.selectedNode instanceof Element) {
      state.selected = elementProbe(state.selectedNode);
      render(state.selectedNode, true);
    }
    return {
      ok: true,
      preview_applied: true,
      selection_count: nodes.length,
      selections,
      source_edits: sourceEdits,
      commit_ready: commitReady,
      error: commitReady ? "" : "every selected element needs a unique data-ui-forge-source before batch commit",
    };
  }

  function targetFromPoint(x, y) {
    const overlayDisplay = state.overlay?.style.display;
    const labelDisplay = state.label?.style.display;
    if (state.overlay) state.overlay.style.display = "none";
    if (state.label) state.label.style.display = "none";
    const node = document.elementFromPoint(x, y);
    if (state.overlay) state.overlay.style.display = overlayDisplay || "none";
    if (state.label) state.label.style.display = labelDisplay || "none";
    return node;
  }

  function onMove(event) {
    if (!state.enabled || state.selected) return;
    const node = targetFromPoint(event.clientX, event.clientY);
    if (!(node instanceof Element)) return;
    state.hovered = node;
    render(node, false);
  }

  function onClick(event) {
    if (!state.enabled) return;
    if (state.preview) revertPreview();
    if (state.batchPreview) revertBatchPreview();
    const node = targetFromPoint(event.clientX, event.clientY);
    if (!(node instanceof Element)) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    const additive = Boolean(event.shiftKey || event.ctrlKey || event.metaKey);
    if (additive) {
      const existing = state.selectedNodes.indexOf(node);
      if (existing >= 0) state.selectedNodes.splice(existing, 1);
      else state.selectedNodes.push(node);
    } else {
      state.selectedNodes = [node];
    }
    state.selected = elementProbe(node);
    state.selectedNode = node;
    state.hovered = node;
    render(node, true);
  }

  function onKey(event) {
    if (!state.enabled) return;
    if (event.key === "Escape") {
      if (state.preview) revertPreview();
      if (state.batchPreview) revertBatchPreview();
      state.selected = null;
      state.selectedNode = null;
      state.selectedNodes = [];
      state.hovered = null;
      render(null);
    }
  }

  document.addEventListener("mousemove", onMove, true);
  document.addEventListener("click", onClick, true);
  document.addEventListener("keydown", onKey, true);

  const api = {
    installed: true,
    enable() {
      state.enabled = true;
      if (state.preview) revertPreview();
      if (state.batchPreview) revertBatchPreview();
      state.selected = null;
      state.selectedNode = null;
      state.selectedNodes = [];
      ensureOverlay();
      return { enabled: true };
    },
    disable() {
      state.enabled = false;
      if (state.preview) revertPreview();
      if (state.batchPreview) revertBatchPreview();
      state.selected = null;
      state.selectedNode = null;
      state.selectedNodes = [];
      state.hovered = null;
      render(null);
      return { enabled: false };
    },
    clear() {
      if (state.preview) revertPreview();
      if (state.batchPreview) revertBatchPreview();
      state.selected = null;
      state.selectedNode = null;
      state.selectedNodes = [];
      if (state.hovered) render(state.hovered, false);
      else render(null);
      return { cleared: true };
    },
    selectByPoint(x, y) {
      const node = targetFromPoint(Number(x), Number(y));
      if (!(node instanceof Element)) return null;
      if (state.preview) revertPreview();
      if (state.batchPreview) revertBatchPreview();
      state.selected = elementProbe(node);
      state.selectedNode = node;
      state.selectedNodes = [node];
      state.hovered = node;
      render(node, true);
      return state.selected;
    },
    select(selector) {
      const node = document.querySelector(selector);
      if (!(node instanceof Element)) return null;
      if (state.preview) revertPreview();
      if (state.batchPreview) revertBatchPreview();
      state.selected = elementProbe(node);
      state.selectedNode = node;
      state.selectedNodes = [node];
      state.hovered = node;
      render(node, true);
      return state.selected;
    },
    selectMany(selectors) {
      if (!Array.isArray(selectors) || !selectors.length) return { ok: false, error: "selectors must be a non-empty array" };
      if (state.preview) revertPreview();
      if (state.batchPreview) revertBatchPreview();
      const nodes = [];
      for (const selector of selectors) {
        const node = document.querySelector(String(selector));
        if (!(node instanceof Element)) return { ok: false, error: `selector did not resolve to an element: ${selector}` };
        if (!nodes.includes(node)) nodes.push(node);
      }
      state.selectedNodes = nodes;
      state.selectedNode = nodes[0];
      state.selected = elementProbe(nodes[0]);
      state.hovered = nodes[0];
      render(nodes[0], true);
      return { ok: true, selection_count: nodes.length, selections: nodes.map(elementProbe) };
    },
    preview(operation) {
      return previewOperation(operation);
    },
    revertPreview() {
      return revertPreview();
    },
    previewMany(operation) {
      return previewMany(operation);
    },
    revertBatchPreview() {
      return revertBatchPreview();
    },
    getPreview() {
      if (!state.preview) return null;
      if (state.preview.operation.type === "style_props") {
        return {
          operation: state.preview.operation,
          source_edit: null,
          style_request: { probe: state.selected, declarations: state.preview.operation.properties, ...(state.preview.operation.state ? { state: state.preview.operation.state } : {}), ...(state.preview.operation.media_chain ? { media_chain: state.preview.operation.media_chain } : {}) },
        };
      }
      return {
        operation: state.preview.operation,
        source_edit: {
          source: state.selected?.ui_forge_source || "",
          operation: state.preview.operation,
        },
      };
    },
    commitSpec() {
      if (!state.preview) return { ok: false, error: "no active preview" };
      if (state.preview.operation.type === "style_props") {
        return {
          ok: false,
          source_edit: null,
          style_request: { probe: state.selected, declarations: state.preview.operation.properties, ...(state.preview.operation.state ? { state: state.preview.operation.state } : {}), ...(state.preview.operation.media_chain ? { media_chain: state.preview.operation.media_chain } : {}) },
          error: "style preview requires CSS ownership resolution through scripts/css_style_editor.mjs",
        };
      }
      const source = state.selected?.ui_forge_source || "";
      return {
        ok: Boolean(source),
        source_edit: { source, operation: state.preview.operation },
        error: source ? "" : "selected element has no data-ui-forge-source; resolve source before commit",
      };
    },
    styleCommitSpec() {
      if (!state.preview || state.preview.operation.type !== "style_props") return { ok: false, error: "no active style_props preview" };
      const probe = state.selected;
      const ok = Boolean(probe && (probe.id || probe.classes?.length));
      return {
        ok,
        style_request: { probe, declarations: state.preview.operation.properties, ...(state.preview.operation.state ? { state: state.preview.operation.state } : {}), ...(state.preview.operation.media_chain ? { media_chain: state.preview.operation.media_chain } : {}) },
        preview_mode: state.preview.operation.state ? "simulated-inline-state-design-preview" : (state.preview.operation.media_chain ? "simulated-inline-responsive-design-preview" : "inline-style-design-preview"),
        error: ok ? "" : "selected element needs an id or class before CSS ownership can be resolved safely",
      };
    },
    commitBatchSpec() {
      if (!state.batchPreview) return { ok: false, error: "no active batch preview", source_edits: [] };
      const selections = state.selectedNodes.filter((node) => node instanceof Element).map(elementProbe);
      const sourceEdits = selections.map((selection) => ({ source: selection.ui_forge_source || "", operation: state.batchPreview.operation }));
      const sources = sourceEdits.map((edit) => edit.source).filter(Boolean);
      const ok = sources.length === selections.length && new Set(sources).size === selections.length;
      return {
        ok,
        source_edits: sourceEdits,
        error: ok ? "" : "every selected element needs a unique data-ui-forge-source before batch commit",
      };
    },
    getSelection() {
      return state.selected;
    },
    getSelections() {
      return state.selectedNodes.filter((node) => node instanceof Element).map(elementProbe);
    },
    probe(selector) {
      const node = document.querySelector(selector);
      return elementProbe(node);
    },
  };

  window.UIForge = api;
  window[KEY] = api;
  return api;
})();
