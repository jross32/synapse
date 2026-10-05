export async function probeTargetSizes(page) {
  return await page.evaluate(() => {
    const visible = (el) => {
      const s = getComputedStyle(el), r = el.getBoundingClientRect();
      return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0 && r.width > 0 && r.height > 0;
    };
    const disabled = (el) => el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('inert') || !!el.closest('[inert]');
    const selector = 'button,a[href],input:not([type="hidden"]),select,textarea,[role="button"],[role="link"],[tabindex]:not([tabindex="-1"])';
    const targets = Array.from(document.querySelectorAll(selector)).filter((el) => visible(el) && !disabled(el));
    const rects = targets.map((el, index) => {
      const r = el.getBoundingClientRect();
      return { el, index, left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height, cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
    });

    const isInlineException = (item) => {
      const el = item.el;
      if (el.tagName !== 'A' && el.getAttribute('role') !== 'link') return false;
      const container = el.closest('p,li,dd,dt,blockquote,figcaption,td,th,label');
      if (!container || container.closest('nav,[role="navigation"],menu')) return false;
      const clone = container.cloneNode(true);
      const matching = Array.from(clone.querySelectorAll('a,[role="link"]'));
      for (const link of matching) link.remove();
      const nonTargetText = (clone.textContent || '').replace(/\s+/g, ' ').trim();
      const style = getComputedStyle(el);
      const lineHeight = parseFloat(style.lineHeight);
      const lineConstrained = Number.isFinite(lineHeight) && lineHeight > 0 && item.height <= lineHeight + 1;
      return Boolean(nonTargetText) && lineConstrained;
    };

    const circleIntersectsRect = (cx, cy, radius, other) => {
      const x = Math.max(other.left, Math.min(cx, other.right));
      const y = Math.max(other.top, Math.min(cy, other.bottom));
      const dx = cx - x, dy = cy - y;
      return (dx * dx + dy * dy) < radius * radius - 0.01;
    };

    const rawSmall = rects.filter((item) => item.width < 24 || item.height < 24);
    const rawSmallSet = new Set(rawSmall.map((item) => item.index));
    const inlineSet = new Set(rawSmall.filter(isInlineException).map((item) => item.index));
    const spacingSet = new Set();
    const failures = [];

    for (const item of rawSmall) {
      if (inlineSet.has(item.index)) continue;
      let intersects = false;
      for (const other of rects) {
        if (other.index === item.index) continue;
        if (rawSmallSet.has(other.index) && !inlineSet.has(other.index)) {
          const dx = item.cx - other.cx, dy = item.cy - other.cy;
          if (Math.hypot(dx, dy) < 24 - 0.01) { intersects = true; break; }
        } else if (circleIntersectsRect(item.cx, item.cy, 12, other)) {
          intersects = true; break;
        }
      }
      if (!intersects) spacingSet.add(item.index);
      else failures.push(item.index);
    }

    return {
      raw_under_24px_target_count: rawSmall.length,
      inline_target_exception_count: inlineSet.size,
      target_spacing_exception_count: spacingSet.size,
      wcag_small_target_count: failures.length,
      target_size_unresolved_exception_note: 'Equivalent-control, essential-presentation, and unmodified user-agent-control exceptions require semantic review and are not auto-applied.'
    };
  });
}
