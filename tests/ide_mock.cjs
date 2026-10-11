// Synthetic VS Code API harness: no editor, source files or agent model used.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ext = require('../nykra/ide_extension/extension.js');
const inbox = process.env.NYKRA_TEST_INBOX;
assert.ok(inbox, 'isolated inbox must be set by test');
const listeners = {};
const privateWorkspace = 'file:///PRIVATE/SECRET_WORKSPACE';
const workspaceUri = { scheme: 'file', toString: () => privateWorkspace };
const folder = { uri: workspaceUri };
const context = { subscriptions: [] };
const vscode = {
  env: { appName: 'Visual Studio Code' },
  workspace: {
    isTrusted: true,
    workspaceFolders: [folder],
    getWorkspaceFolder: () => folder,
    onDidSaveTextDocument: fn => { listeners.save = fn; return { dispose() {} }; },
  },
  tasks: {
    onDidStartTask: fn => { listeners.start = fn; return { dispose() {} }; },
    onDidEndTaskProcess: fn => { listeners.end = fn; return { dispose() {} }; },
  },
};
const stats = ext.activate(context, { vscode, inbox });
assert.equal(context.subscriptions.length, 3);
listeners.save({ uri: { scheme: 'file', toString: () => privateWorkspace + '/PRIVATE_FILE.js' } });
listeners.save({ uri: { scheme: 'untitled', toString: () => 'untitled:SECRET' } });
const exec = {};
listeners.start({ execution: exec });
listeners.end({ execution: exec, exitCode: 1 });
vscode.workspace.isTrusted = false;
listeners.save({ uri: { scheme: 'file' } }); // trust revocation: ignored
assert.equal(stats.recorded, 2);
assert.ok(stats.ignored >= 2);
const paths = fs.readdirSync(inbox);
assert.equal(paths.length, 2);
for (const name of paths) {
  const payload = fs.readFileSync(path.join(inbox, name), 'utf8');
  assert.ok(!payload.includes('SECRET'));
  assert.ok(!payload.includes('PRIVATE'));
  const obj = JSON.parse(payload);
  assert.equal(obj.source, 'ide-vscode');
  assert.match(obj.task_id, /^ws-[a-f0-9]{24}$/);
  assert.ok(['document_save', 'task_completed'].includes(obj.tool));
}
console.log(JSON.stringify({ generated: paths.length, version: stats.version, ignored: stats.ignored }));
