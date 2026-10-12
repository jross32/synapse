'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const configPath = path.join(root, 'installer', 'release-python.local.json');
const lockPath = path.join(root, 'requirements-release-windows.lock');
const canonical = name => name.toLowerCase().replace(/_/g, '-');
function resolvePython() {
  const config = fs.existsSync(configPath) ? JSON.parse(fs.readFileSync(configPath, 'utf8')) : {};
  const python = process.env.SYNAPSE_RELEASE_PYTHON || config.pythonExecutable;
  if (!python || !path.isAbsolute(python) || !fs.existsSync(python)) {
    throw new Error('Configure a dedicated release Python with node scripts/release-python.cjs --ensure.');
  }
  return python;
}
function environmentReceipt(python = resolvePython()) {
  const script = "import json,platform; from importlib import metadata; print(json.dumps({'pythonVersion':platform.python_version(),'packages':sorted((d.metadata['Name'],d.version) for d in metadata.distributions() if d.metadata['Name'].lower().replace('_','-') not in {'synapse-daemon','pip'})}))";
  const report = JSON.parse(execFileSync(python, ['-c', script], { encoding: 'utf8', timeout: 30000, windowsHide: true }));
  const installed = new Map(report.packages.map(([name, version]) => [canonical(name), version]));
  for (const line of fs.readFileSync(lockPath, 'utf8').split(/\r?\n/)) {
    if (!line.trim() || line.startsWith('#')) continue;
    const match = line.match(/^([A-Za-z0-9_.-]+)==([^\s;]+)$/);
    if (!match) throw new Error('Invalid release dependency lock entry.');
    if (installed.get(canonical(match[1])) !== match[2]) throw new Error('Release dependency differs from lock: ' + match[1]);
  }
  const required = new Map(fs.readFileSync(lockPath, 'utf8').split(/\r?\n/).map(line => line.match(/^([A-Za-z0-9_.-]+)==([^\s;]+)$/)).filter(Boolean).map(match => [canonical(match[1]), match[2]]));
  if (installed.size !== required.size) throw new Error('Release environment contains unreviewed dependencies; use a fresh dedicated environment.');
  if (!/^3\.12\./.test(report.pythonVersion)) throw new Error('This Windows release lock is validated for Python 3.12.');
  report.packages = report.packages.map(([name, version]) => [canonical(name), version]).sort((a, b) => a[0].localeCompare(b[0]));
  return { ...report, sha256: crypto.createHash('sha256').update(JSON.stringify(report)).digest('hex') };
}
function ensureEnvironment() {
  if (process.platform !== 'win32') throw new Error('This release environment targets Windows.');
  if (process.env.SYNAPSE_RELEASE_PYTHON || fs.existsSync(configPath)) {
    const receipt = environmentReceipt();
    console.log(JSON.stringify(receipt));
    return;
  }
  const directory = path.join(root, '.release-venv');
  const python = path.join(directory, 'Scripts', 'python.exe');
  if (!fs.existsSync(python)) {
    execFileSync('py', ['-3.12', '-m', 'venv', directory], { stdio: 'inherit', windowsHide: true });
    execFileSync(python, ['-m', 'pip', 'install', '-r', lockPath, '-e', '.[dev,build]'], { cwd: root, stdio: 'inherit', windowsHide: true });
  }
  const receipt = environmentReceipt(python);
  fs.writeFileSync(configPath, JSON.stringify({ pythonExecutable: python }, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
}
module.exports = { resolvePython, environmentReceipt, ensureEnvironment };
if (require.main === module) {
  if (process.argv[2] === '--ensure') ensureEnvironment();
  else console.log(JSON.stringify(environmentReceipt()));
}
