/**
 * Minimal static server for the premium installer shell.
 * Serves installer/premium-shell/ at http://localhost:3457
 * Used by the Playwright screenshot script and for local preview.
 */
'use strict';

const http = require('http');
const fs   = require('fs');
const path = require('path');

const PORT = 3457;
const ROOT = __dirname;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.svg':  'image/svg+xml',
  '.png':  'image/png',
  '.ico':  'image/x-icon',
};

const server = http.createServer((req, res) => {
  let urlPath = req.url.split('?')[0].split('#')[0];
  if (urlPath === '/' || urlPath === '') urlPath = '/index.html';

  const filePath = path.join(ROOT, urlPath.replace(/\.\./g, '')); // no path traversal
  const ext = path.extname(filePath).toLowerCase();
  const mime = MIME[ext] || 'application/octet-stream';

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end(`404 Not Found: ${urlPath}`);
      return;
    }
    res.writeHead(200, { 'Content-Type': mime, 'Cache-Control': 'no-store' });
    res.end(data);
  });
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[serve] Synapse installer shell → http://127.0.0.1:${PORT}`);
  console.log(`[serve] Press Ctrl+C to stop.`);
});

module.exports = server;
