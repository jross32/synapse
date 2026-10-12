'use strict';
const assert = require('node:assert/strict');
const http = require('node:http');
const { awaitMatchingDaemonVersion, probe } = require('./daemon-version-check.cjs');
(async() => {
 let version='0.1.209';
 const server=http.createServer((_req,res)=>{
   res.setHeader('Content-Type','application/json');
   res.end(JSON.stringify({ok:true,version}));
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const port=server.address().port;
 try {
  assert.deepEqual(await probe(port,500),{status:'ready',version:'0.1.209'});
  await assert.rejects(awaitMatchingDaemonVersion('0.2.219',{port,deadlineMs:140,intervalMs:20}),/running v0\.1\.209/);
  version='0.2.219';
  assert.deepEqual(await awaitMatchingDaemonVersion('0.2.219',{port,deadlineMs:300,intervalMs:20}),{ok:true,version:'0.2.219'});
  version='0.1.209';setTimeout(()=>{version='0.2.219'},90);
  assert.equal((await awaitMatchingDaemonVersion('0.2.219',{port,deadlineMs:400,intervalMs:15})).ok,true);
  await assert.rejects(awaitMatchingDaemonVersion('bad',{port}),/Invalid expected/);
  await assert.rejects(awaitMatchingDaemonVersion('0.2.219',{port:0}),/Invalid daemon probe/);
  console.log('PASS daemon version check: active version, old daemon failure, recovery, invalid input');
 } finally { await new Promise(resolve=>server.close(resolve)); }
})().catch(err=>{console.error(err);process.exitCode=1});
