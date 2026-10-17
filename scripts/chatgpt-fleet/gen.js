async (page) => {
  const ids = OWNED_IDS;
  const out = [];
  for (const p of page.context().pages()) {
    const id = ids.find(i => p.url().includes('/c/' + i));
    if (!id) continue;
    const gen = await p.locator('[data-testid="stop-button"], button[aria-label*="Stop" i]').count();
    const last = await p.evaluate(() => { const m = document.querySelector('main'); const t = m ? m.innerText : ''; const i = t.lastIndexOf('HANDOFF'); return i >= 0 ? t.slice(i, i + 420).replace(/\s+/g, ' ') : t.replace(/\s+/g, ' ').slice(-200); });
    out.push(id + ' gen=' + gen + ' | ' + last);
  }
  return out.join('\n');
}
