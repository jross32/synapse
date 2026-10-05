import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { buildHtmlReport, prepareReportData } from './reporting.mjs';

const root = await mkdtemp(path.join(os.tmpdir(), 'uds-report-assets-'));
try {
  const sourceDir = path.join(root, 'source');
  const reportDir = path.join(root, 'report');
  await import('node:fs/promises').then(({ mkdir }) => Promise.all([mkdir(sourceDir), mkdir(reportDir)]));
  const source = path.join(sourceDir, 'scene.png');
  await writeFile(source, Buffer.from('real-evidence-bytes'));

  const prepared = await prepareReportData({
    target_input: 'Asset proof',
    scenes: [
      { label: 'Available scene', url: 'http://example.test/one', screenshot: source },
      { label: 'Missing scene', url: 'http://example.test/two', screenshot: path.join(sourceDir, 'missing.png') },
    ],
  }, reportDir);

  assert.equal(prepared.scenes[0].screenshot_available, true);
  assert.equal(prepared.scenes[0].screenshot_copied_for_report, true);
  assert.equal(path.dirname(prepared.scenes[0].screenshot), reportDir);
  assert.equal((await readFile(prepared.scenes[0].screenshot)).toString(), 'real-evidence-bytes');
  assert.equal(prepared.scenes[1].screenshot, null);
  assert.equal(prepared.scenes[1].screenshot_available, false);

  const score = {
    overall_score: 90,
    grade: 'A',
    validity: { status: 'not_applicable' },
    scores: { ui: 90, ux: 90, performance: 90, accessibility: 90, reliability: 90 },
    gates: [],
    metrics: {},
  };
  const html = buildHtmlReport(prepared, score, null);
  assert.match(html, /\.\/scene\.png/);
  assert.match(html, /Screenshot unavailable/);
  assert.match(html, /1 screenshot asset\(s\) available in this report bundle/);
  assert.doesNotMatch(html, /missing\.png/);
  console.log('reporting.assets.test.mjs: PASS');
} finally {
  await rm(root, { recursive: true, force: true });
}
