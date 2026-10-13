const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('C:/Users/justi/synapse/node_modules/typescript');
const source = fs.readFileSync(require('node:path').join(__dirname, '../renderer/lib/first-launch-state.ts'), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const moduleExports = {};
vm.runInNewContext(js, { exports: moduleExports });
const { freshProgress, parseProgress, advanceProgress, retreatProgress, readProgress, saveProgress, ONBOARDING_KEY } = moduleExports;
test('fresh install begins at welcome and is not completed', () => {
  assert.equal(readProgress({ getItem: () => null }).step, 'welcome');
  assert.equal(freshProgress().completed, false);
  assert.equal(freshProgress().mode, 'undecided');
});
test('interrupted setup resumes saved step, mode, and companion', () => {
  let saved = null;
  const store = { getItem: () => saved, setItem: (key, value) => { assert.equal(key, ONBOARDING_KEY); saved = value; } };
  const progress = { ...freshProgress(), step: 'companion', mode: 'guest', companion: 'ninja' };
  assert.equal(saveProgress(store, progress), true);
  assert.deepEqual(JSON.parse(JSON.stringify(readProgress(store))), progress);
});
test('corrupt or unsupported progress is reset safely', () => {
  assert.equal(parseProgress('invalid').step, 'welcome');
  assert.equal(parseProgress(JSON.stringify({ version: 99, completed: true })).completed, false);
  assert.equal(parseProgress(JSON.stringify({ ...freshProgress(), step: 'bogus' })).step, 'welcome');
});
test('step transitions are bounded', () => {
  assert.equal(retreatProgress(freshProgress()).step, 'welcome');
  assert.equal(advanceProgress(freshProgress()).step, 'account');
  assert.equal(advanceProgress({ ...freshProgress(), step: 'ready' }).step, 'ready');
});
test('completed setup survives upgrades with same storage schema', () => {
  const completed = { ...freshProgress(), step: 'ready', mode: 'account', completed: true };
  assert.equal(parseProgress(JSON.stringify(completed)).completed, true);
});
test('storage unavailable fails without crashing', () => {
  assert.equal(readProgress({ getItem() { throw Error('denied'); } }).completed, false);
  assert.equal(saveProgress({ setItem() { throw Error('denied'); } }, freshProgress()), false);
});

test('account selection cannot be bypassed with Next', () => {
  const { canAdvanceWithNext } = moduleExports;
  assert.equal(canAdvanceWithNext({ ...freshProgress(), step: 'account' }, false), false);
  assert.equal(canAdvanceWithNext({ ...freshProgress(), step: 'computer' }, true), false);
  assert.equal(canAdvanceWithNext({ ...freshProgress(), step: 'computer' }, false), true);
  assert.equal(canAdvanceWithNext({ ...freshProgress(), step: 'ready' }, false), false);
});

test('companion setting persists only allowed IDs', () => {
  const { readCompanion, saveCompanion, COMPANION_KEY } = moduleExports;
  const values = new Map();
  const store = { getItem(key) { return values.get(key) ?? null; }, setItem(key, value) { values.set(key, value); } };
  assert.equal(readCompanion(store), null);
  assert.equal(saveCompanion(store, 'ninja'), true);
  assert.equal(values.get(COMPANION_KEY), 'ninja');
  assert.equal(readCompanion(store), 'ninja');
  assert.equal(saveCompanion(store, 'untrusted'), false);
  assert.equal(readCompanion(store), 'ninja');
  assert.equal(saveCompanion(store, null), true);
  assert.equal(readCompanion(store), null);
});
test('companion storage unavailable is handled safely', () => {
  const { readCompanion, saveCompanion } = moduleExports;
  assert.equal(readCompanion({getItem() { throw Error('blocked'); }}), null);
  assert.equal(saveCompanion({setItem() { throw Error('blocked'); }}, 'nova'), false);
});
