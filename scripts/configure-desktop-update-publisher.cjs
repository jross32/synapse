#!/usr/bin/env node
'use strict';
// Embeds PUBLIC publisher trust in packaged Electron. Private signing keys
// are never loaded, created, or shipped by this build step.
const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const feed = 'https://download.whatapc.com/updates/stable.json';
const publicFile = path.join(root, 'electron', 'update-publisher-public.pem');
const output = path.join(root, 'dist-electron', 'update-publisher.json');
const url = new URL(feed);
if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash)
  throw new Error('Invalid HTTPS publisher feed');
const publicKey = fs.readFileSync(publicFile, 'utf8');
if (crypto.createPublicKey(publicKey).asymmetricKeyType !== 'ed25519')
  throw new Error('Expected an Ed25519 public verification key');
const data = JSON.stringify({schema: 1, feed_url: feed, public_key: publicKey}) + '\n';
if (fs.existsSync(output) && fs.readFileSync(output, 'utf8') !== data)
  throw new Error('Different bundled update publisher is already present');
fs.mkdirSync(path.dirname(output), {recursive: true});
if (!fs.existsSync(output)) fs.writeFileSync(output, data, {flag: 'wx'});
console.log(JSON.stringify({ok:true,feedUrl:feed,publicKeySha256:crypto.createHash('sha256').update(publicKey).digest('hex')}));
