const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const esbuild = require('esbuild');
const path = require('node:path');

async function main() {
  const built = esbuild.buildSync({
    entryPoints: ['renderer/components/StaffHQObs.tsx'],
    bundle: true, write: false, platform: 'node', format: 'cjs',
    external: ['react', 'lucide-react'], logLevel: 'silent',
  });
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, mod, mod.exports);
  const { ObsLink, obsAuthentication } = mod.exports;
  globalThis.crypto = crypto.webcrypto;

  const password = 'known-local-test-only';
  const salt = 'salt-data';
  const challenge = 'challenge-data';
  const secret = crypto.createHash('sha256').update(password + salt).digest('base64');
  const expected = crypto.createHash('sha256').update(secret + challenge).digest('base64');
  assert.equal(await obsAuthentication(password, salt, challenge), expected);

  const observed = [];
  class FakeWebSocket {
    static OPEN = 1;
    constructor(url) {
      assert.equal(url, 'ws://127.0.0.1:4455');
      this.readyState = FakeWebSocket.OPEN;
      setTimeout(() => this.onmessage?.({
        data: JSON.stringify({ op: 0, d: { rpcVersion: 1, authentication: { salt, challenge } } }),
      }), 0);
    }
    send(raw) {
      const m = JSON.parse(raw);
      observed.push(m);
      if (m.op === 1) {
        assert.equal(m.d.authentication, expected);
        setTimeout(() => this.onmessage?.({ data: JSON.stringify({ op: 2, d: { negotiatedRpcVersion: 1 } }) }), 0);
      }
      if (m.op === 6) {
        let data = {};
        if (m.d.requestType === 'GetSceneList') data = { scenes: [{sceneName: 'Live'}, {sceneName: 'BRB'}], currentProgramSceneName: 'Live' };
        if (m.d.requestType === 'GetStreamStatus') data = { outputActive: false };
        if (m.d.requestType === 'SetCurrentProgramScene') assert.equal(m.d.requestData.sceneName, 'BRB');
        setTimeout(() => this.onmessage?.({
          data: JSON.stringify({ op: 7, d: { requestId: m.d.requestId, requestType: m.d.requestType, requestStatus: { result: true }, responseData: data } }),
        }), 0);
      }
    }
    close() {
      this.readyState = 3;
      this.onclose?.({});
    }
  }
  globalThis.WebSocket = FakeWebSocket;
  const link = new ObsLink();
  await link.connect(password);
  const scenes = await link.request('GetSceneList');
  assert.equal(scenes.currentProgramSceneName, 'Live');
  assert.equal(scenes.scenes.length, 2);
  const stream = await link.request('GetStreamStatus');
  assert.equal(stream.outputActive, false);
  await link.request('SetCurrentProgramScene', { sceneName: 'BRB' });
  assert.deepEqual(observed.filter(m => m.op === 6).map(m => m.d.requestType),
    ['GetSceneList', 'GetStreamStatus', 'SetCurrentProgramScene']);
  link.disconnect();
  console.log('OBS_PROTOCOL_SMOKE_OK auth, identify, list, stream status, explicit scene action');
}
main().catch(e => { console.error(e); process.exitCode = 1; });
