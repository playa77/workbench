// Version: 0.1.0
// electron-builder afterPack hook.
// Renames the Electron binary to .bin and replaces it with a wrapper script
// that passes --no-sandbox, solving the SUID sandbox error on Ubuntu 24.04.
const fs = require('fs');
const path = require('path');

exports.default = async function (context) {
  if (context.electronPlatformName !== 'linux') return;

  const appDir = context.appOutDir;
  const execName = context.packager.appInfo.name;

  const binPath = path.join(appDir, execName);
  const binReal = binPath + '.bin';

  if (!fs.existsSync(binPath)) {
    console.error(`[after-pack] Binary not found: ${binPath}`);
    return;
  }

  fs.renameSync(binPath, binReal);

  const wrapper = [
    '#!/usr/bin/env bash',
    'set -euo pipefail',
    'DIR="$(cd "$(dirname "$0")" && pwd)"',
    `exec "\${DIR}/${execName}.bin" --no-sandbox "$@"`,
    '',
  ].join('\n');

  fs.writeFileSync(binPath, wrapper);
  fs.chmodSync(binPath, 0o755);

  console.log(`[after-pack] Wrapped ${execName} with --no-sandbox`);
};
