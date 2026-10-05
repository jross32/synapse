export async function probeKeyboard(page, options = {}) {
  const maxTabs = Math.max(1, Math.min(40, Number(options.maxTabs) || 20));
  const setup = await page.evaluate((limit) => {
    const visible = (el) => {
      const s = getComputedStyle(el), r = el.getBoundingClientRect();
      return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0 && r.width > 0 && r.height > 0;
    };
    const disabled = (el) => el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('inert') || !!el.closest('[inert]');
    const focusables = Array.from(document.querySelectorAll('a[href],button,input:not([type="hidden"]),select,textarea,[tabindex]'))
      .filter((el) => visible(el) && !disabled(el) && Number(el.getAttribute('tabindex') ?? 0) >= 0 && el.getAttribute('aria-hidden') !== 'true');
    focusables.forEach((el, index) => el.setAttribute('data-uds-keyboard-id', String(index)));
    const dialogs = Array.from(document.querySelectorAll('dialog,[role="dialog"],[aria-modal="true"]')).filter(visible);
    const initialActiveId = document.activeElement?.getAttribute?.('data-uds-keyboard-id') ?? null;
    if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur?.();
    return { focusable_count: focusables.length, expected_sample: Math.min(limit, focusables.length), dialog_count: dialogs.length, initial_active_id: initialActiveId };
  }, maxTabs).catch(() => ({ focusable_count: 0, expected_sample: 0, dialog_count: 0 }));

  const reached = new Set(setup.initial_active_id !== null && setup.initial_active_id !== undefined ? [String(setup.initial_active_id)] : []);
  let tested = 0, visiblePass = 0, notObscuredPass = 0, dialogEscapes = 0;
  const samples = [];
  const iterations = Math.max(1, setup.expected_sample || Math.min(maxTabs, 8));

  for (let i = 0; i < iterations; i += 1) {
    await page.keyboard.press('Tab').catch(() => undefined);
    await page.waitForFunction(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return true;
      const r = el.getBoundingClientRect();
      return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
    }, { timeout: 650 }).catch(() => undefined);
    await page.waitForTimeout(30);
    const row = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      const r = el.getBoundingClientRect(), s = getComputedStyle(el);
      const focusVisible = (() => { try { return el.matches(':focus-visible'); } catch { return false; } })();
      const outlineWidth = parseFloat(s.outlineWidth) || 0;
      const outline = s.outlineStyle !== 'none' && outlineWidth > 0 && s.outlineColor !== 'transparent';
      const shadow = String(s.boxShadow || 'none') !== 'none';
      const indicator = focusVisible && (outline || shadow);
      const left = Math.max(0, r.left), right = Math.min(innerWidth - 1, r.right), top = Math.max(0, r.top), bottom = Math.min(innerHeight - 1, r.bottom);
      let notObscured = false;
      if (right > left && bottom > top) {
        const pts = [
          [(left + right) / 2, (top + bottom) / 2],
          [left + 1, top + 1], [right - 1, top + 1], [left + 1, bottom - 1], [right - 1, bottom - 1]
        ];
        notObscured = pts.some(([x, y]) => {
          const hit = document.elementFromPoint(Math.max(0, Math.min(innerWidth - 1, x)), Math.max(0, Math.min(innerHeight - 1, y)));
          return !!hit && (hit === el || el.contains(hit) || hit.contains(el));
        });
      }
      const dialogs = Array.from(document.querySelectorAll('dialog,[role="dialog"],[aria-modal="true"]')).filter((d) => {
        const st = getComputedStyle(d), rr = d.getBoundingClientRect();
        return st.display !== 'none' && st.visibility !== 'hidden' && rr.width > 0 && rr.height > 0;
      });
      const insideDialog = dialogs.length ? dialogs.some((d) => d === el || d.contains(el)) : null;
      return {
        id: el.getAttribute('data-uds-keyboard-id'),
        tag: el.tagName.toLowerCase(),
        label: (el.getAttribute('aria-label') || el.textContent || el.getAttribute('value') || '').trim().replace(/\s+/g, ' ').slice(0, 80),
        focus_visible_match: focusVisible,
        visible_indicator: indicator,
        not_fully_obscured: notObscured,
        inside_visible_dialog: insideDialog
      };
    }).catch(() => null);
    if (!row) continue;
    tested += 1;
    if (row.id !== null) reached.add(row.id);
    if (row.visible_indicator) visiblePass += 1;
    if (row.not_fully_obscured) notObscuredPass += 1;
    if (row.inside_visible_dialog === false) dialogEscapes += 1;
    if (samples.length < 12) samples.push(row);
  }

  let escapeDismissed = null;
  if (setup.dialog_count > 0) {
    const before = setup.dialog_count;
    await page.keyboard.press('Escape').catch(() => undefined);
    await page.waitForTimeout(120);
    const after = await page.evaluate(() => Array.from(document.querySelectorAll('dialog,[role="dialog"],[aria-modal="true"]')).filter((d) => {
      const st = getComputedStyle(d), r = d.getBoundingClientRect();
      return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0;
    }).length).catch(() => before);
    escapeDismissed = after < before;
  }

  return {
    focusable_count: setup.focusable_count,
    expected_sample: setup.expected_sample,
    reached_count: reached.size,
    tested_focus_steps: tested,
    visible_focus_count: visiblePass,
    not_obscured_count: notObscuredPass,
    dialog_count: setup.dialog_count,
    dialog_focus_escape_count: dialogEscapes,
    dialog_focus_contained: setup.dialog_count > 0 ? dialogEscapes === 0 : null,
    dialog_escape_dismissed: escapeDismissed,
    samples
  };
}
