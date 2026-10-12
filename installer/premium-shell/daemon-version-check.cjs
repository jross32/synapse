'use strict';
/**
 * Post-install runtime check: app files on disk are not evidence that the
 * correct Synapse daemon is listening. Never terminate or replace a running
 * daemon here; failures remain actionable and preserve the user's work.
 */
const http = require('node:http');

function probe(port, timeoutMs) {
  return new Promise(resolve => {
    const request = http.get({
      hostname: '127.0.0.1',
      port,
      path: '/api/v1/health',
      agent: false,
      timeout: timeoutMs,
      headers: { Accept: 'application/json' },
    }, response => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', part => {
        body += part;
        if (body.length > 4096) request.destroy(new Error('Unexpected response size'));
      });
      response.on('end', () => {
        if (response.statusCode !== 200) return resolve({ status: 'unreachable' });
        try {
          const json = JSON.parse(body);
          if (json.ok === true && /^\d+\.\d+\.\d+$/.test(json.version)) {
            return resolve({ status: 'ready', version: json.version });
          }
        } catch (_) {}
        resolve({ status: 'unreachable' });
      });
    });
    request.on('timeout', () => request.destroy(new Error('Timeout')));
    request.on('error', () => resolve({ status: 'unreachable' }));
  });
}

async function awaitMatchingDaemonVersion(expected, opts = {}) {
  if (typeof expected !== 'string' || !/^\d+\.\d+\.\d+$/.test(expected)) {
    throw new Error('Invalid expected Synapse daemon version');
  }
  const port = opts.port ?? 7878;
  const deadlineMs = opts.deadlineMs ?? 25000;
  const intervalMs = opts.intervalMs ?? 700;
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535
      || !Number.isSafeInteger(deadlineMs) || deadlineMs < 100 || deadlineMs > 60000
      || !Number.isSafeInteger(intervalMs) || intervalMs < 1 || intervalMs > 10000) {
    throw new Error('Invalid daemon probe options');
  }
  const deadline = Date.now() + deadlineMs;
  let lastSeen = null;
  do {
    const result = await probe(port, Math.min(1200, Math.max(100, deadlineMs)));
    if (result.status === 'ready' && result.version === expected) {
      return { ok: true, version: expected };
    }
    if (result.status === 'ready') lastSeen = result.version;
    const delay = Math.min(intervalMs, Math.max(0, deadline - Date.now()));
    if (delay) await new Promise(resolve => setTimeout(resolve, delay));
  } while (Date.now() < deadline);
  if (lastSeen) {
    throw new Error('Synapse ' + expected + ' was installed, but the background service is still running v' + lastSeen
      + '. Quit the old Synapse app, reopen the new installation, and verify the service version before attempting account or device sync. Your local projects have not been removed.');
  }
  throw new Error('Synapse ' + expected + ' was installed, but its background service did not become reachable.'
    + ' Reopen Synapse and check the connection in Settings before attempting device sync. Your local projects have not been removed.');
}
module.exports = { probe, awaitMatchingDaemonVersion };
