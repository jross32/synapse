(() => {
  const KEY = "UIForgeAudit";
  if (window[KEY]?.run) return window[KEY];

  const INTERACTIVE = [
    "a[href]",
    "button",
    "input:not([type='hidden'])",
    "select",
    "textarea",
    "[role='button']",
    "[role='link']",
    "[role='checkbox']",
    "[role='radio']",
    "[role='switch']",
    "[tabindex]:not([tabindex='-1'])",
  ].join(",");

  function visible(el) {
    if (el.getAttribute && el.getAttribute("aria-hidden") === "true") return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
  }

  function text(el) {
    return String(el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 160);
  }

  function accessibleName(el) {
    return (
      el.getAttribute("aria-label") ||
      el.getAttribute("alt") ||
      el.getAttribute("title") ||
      (el.labels && el.labels.length ? Array.from(el.labels).map((x) => text(x)).join(" ") : "") ||
      text(el)
    ).trim().slice(0, 160);
  }

  function selectorHint(el) {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const testid = el.getAttribute("data-testid");
    if (testid) return `[data-testid=${JSON.stringify(testid)}]`;
    const source = el.getAttribute("data-ui-forge-source");
    if (source) return `[data-ui-forge-source=${JSON.stringify(source)}]`;
    const classes = Array.from(el.classList || []).slice(0, 3).map((x) => `.${CSS.escape(x)}`).join("");
    return `${el.tagName.toLowerCase()}${classes}`;
  }

  function rectData(el) {
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height, top: r.top, right: r.right, bottom: r.bottom, left: r.left };
  }

  function overflowAudit() {
    const viewportWidth = document.documentElement.clientWidth;
    const pageOverflow = Math.max(0, document.documentElement.scrollWidth - viewportWidth);
    const offenders = [];
    if (pageOverflow <= 1) return { page_overflow_px: pageOverflow, offenders };
    for (const el of document.querySelectorAll("body *")) {
      if (!visible(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.right > viewportWidth + 1 || r.left < -1) {
        offenders.push({ selector: selectorHint(el), tag: el.tagName.toLowerCase(), rect: rectData(el), text: text(el) });
        if (offenders.length >= 30) break;
      }
    }
    return { page_overflow_px: pageOverflow, offenders };
  }

  function interactiveAudit() {
    const smallTargets = [];
    const missingNames = [];
    const controls = [];
    for (const el of document.querySelectorAll(INTERACTIVE)) {
      if (!visible(el)) continue;
      const r = el.getBoundingClientRect();
      const name = accessibleName(el);
      const info = {
        selector: selectorHint(el),
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute("role") || "",
        name,
        rect: rectData(el),
        disabled: Boolean(el.disabled || el.getAttribute("aria-disabled") === "true"),
      };
      controls.push(info);
      if (r.width < 44 || r.height < 44) smallTargets.push(info);
      if (!name) missingNames.push(info);
    }
    return { visible_count: controls.length, small_targets: smallTargets.slice(0, 50), missing_names: missingNames.slice(0, 50) };
  }

  function formAudit() {
    const unlabeled = [];
    for (const el of document.querySelectorAll("input:not([type='hidden']), select, textarea")) {
      if (!visible(el)) continue;
      const hasLabel = Boolean(
        (el.labels && el.labels.length) ||
        el.getAttribute("aria-label") ||
        el.getAttribute("aria-labelledby") ||
        el.getAttribute("title")
      );
      if (!hasLabel) {
        unlabeled.push({ selector: selectorHint(el), tag: el.tagName.toLowerCase(), type: el.getAttribute("type") || "", rect: rectData(el) });
      }
    }
    return { unlabeled_controls: unlabeled.slice(0, 50) };
  }

  function imageAudit() {
    const missingAlt = [];
    for (const el of document.querySelectorAll("img")) {
      if (!visible(el)) continue;
      if (!el.hasAttribute("alt")) {
        missingAlt.push({ selector: selectorHint(el), src: String(el.currentSrc || el.src || "").slice(0, 240), rect: rectData(el) });
      }
    }
    return { missing_alt: missingAlt.slice(0, 50) };
  }

  function headingAudit() {
    const headings = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6"))
      .filter(visible)
      .map((el) => ({ level: Number(el.tagName.slice(1)), text: text(el), selector: selectorHint(el) }));
    const h1s = headings.filter((x) => x.level === 1);
    const levelJumps = [];
    for (let i = 1; i < headings.length; i++) {
      if (headings[i].level - headings[i - 1].level > 1) levelJumps.push({ from: headings[i - 1], to: headings[i] });
    }
    return { headings, h1_count: h1s.length, level_jumps: levelJumps };
  }


  function incompletenessAudit() {
    const prototypePattern = /\b(coming\s+soon|next\s+(?:ui\s+)?slice|local\s+fallback|not\s+connected|placeholder|todo)\b/i;
    const disabledControls = [];
    const prototypeSignals = [];
    const noOpLinks = [];
    for (const el of document.querySelectorAll(INTERACTIVE)) {
      if (!visible(el)) continue;
      const info = {
        selector: selectorHint(el),
        tag: el.tagName.toLowerCase(),
        name: accessibleName(el),
        text: text(el),
        rect: rectData(el),
      };
      if (el.disabled || el.getAttribute("aria-disabled") === "true") disabledControls.push(info);
      const href = el.getAttribute("href");
      if (el.tagName.toLowerCase() === "a" && (href === "#" || /^javascript:/i.test(href || ""))) noOpLinks.push({ ...info, href: href || "" });
    }
    for (const el of document.querySelectorAll("body *")) {
      if (!visible(el)) continue;
      const value = text(el);
      if (!value || value.length > 240) continue;
      const match = value.match(prototypePattern);
      if (match) {
        prototypeSignals.push({ selector: selectorHint(el), signal: match[0], text: value, rect: rectData(el) });
        if (prototypeSignals.length >= 50) break;
      }
    }
    return {
      disabled_controls: disabledControls.slice(0, 50),
      prototype_signals: prototypeSignals,
      no_op_links: noOpLinks.slice(0, 50),
    };
  }

  function run() {
    const overflow = overflowAudit();
    const interactive = interactiveAudit();
    const forms = formAudit();
    const images = imageAudit();
    const headings = headingAudit();
    const incompleteness = incompletenessAudit();
    const violations = {
      horizontal_overflow: overflow.page_overflow_px > 1,
      small_target_count: interactive.small_targets.length,
      missing_interactive_name_count: interactive.missing_names.length,
      unlabeled_form_control_count: forms.unlabeled_controls.length,
      missing_image_alt_count: images.missing_alt.length,
      heading_level_jump_count: headings.level_jumps.length,
      h1_count: headings.h1_count,
      disabled_control_count: incompleteness.disabled_controls.length,
      prototype_signal_count: incompleteness.prototype_signals.length,
      no_op_link_count: incompleteness.no_op_links.length,
    };
    return {
      schema: "ui-forge-browser-audit-v2",
      url: location.href,
      title: document.title,
      viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
      document: { scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight },
      violations,
      overflow,
      interactive,
      forms,
      images,
      headings,
      incompleteness,
      captured_at: new Date().toISOString(),
    };
  }

  const api = { run };
  window[KEY] = api;
  return api;
})();
