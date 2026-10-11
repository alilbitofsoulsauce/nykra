'use strict';
/**
 * Nykra passive editor adapter (VS Code API).
 * An IDE event is not an AI action or a scored discovery.
 * No content, file paths, task labels, prompts, outputs, or raw URIs leave here.
 */
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { randomUUID, createHash } = crypto;

const EXTENSION_VERSION = '0.16.0';
const MAX_PENDING_EVENTS = 500;

function home() {
  if (process.env.NYKRA_HOME) return path.resolve(process.env.NYKRA_HOME);
  if (process.platform === 'win32') return path.join(
    process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'), 'Nykra'
  );
  return path.join(process.env.XDG_STATE_HOME || path.join(os.homedir(), '.local', 'state'), 'nykra');
}

function editorId(appName) {
  const name = String(appName || '').toLowerCase();
  if (name.includes('windsurf')) return 'windsurf';
  if (name.includes('cursor')) return 'cursor';
  if (name.includes('vscodium')) return 'vscodium';
  if (name.includes('code')) return 'vscode';
  return 'vscode-compatible';
}

function workspaceId(uri) {
  const raw = String(uri?.toString?.() || '');
  if (!raw) return null;
  return 'ws-' + createHash('sha256').update(raw).digest('hex').slice(0, 24);
}

function isTrustedWorkspace(vscode) {
  return vscode?.workspace?.isTrusted === true &&
    Array.isArray(vscode.workspace.workspaceFolders) &&
    vscode.workspace.workspaceFolders.length > 0;
}

/** Write only allowlisted records through an atomic, bounded spool. */
function enqueue(record, options = {}) {
  const dir = options.inbox || path.join(home(), 'ide-inbox');
  if (!record || typeof record !== 'object') return false;
  const keys = Object.keys(record).sort().join(',');
  if (keys !== 'duration_ms,event_id,outcome,source,task_id,tool') return false;
  if (!/^ide-(vscode|cursor|windsurf|vscodium|vscode-compatible)$/.test(record.source)) return false;
  if (!/^ws-[a-f0-9]{24}$/.test(record.task_id)) return false;
  if (!/^(document_save|task_completed)$/.test(record.tool)) return false;
  if (!/^(succeeded|failed)$/.test(record.outcome)) return false;
  if (typeof record.duration_ms !== 'number' || !Number.isFinite(record.duration_ms) || record.duration_ms < 0) return false;
  if (!/^ide-[a-f0-9-]{36}$/.test(record.event_id)) return false;
  try {
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    const fileCount = fs.readdirSync(dir, { withFileTypes: true })
      .filter(entry => entry.isFile() && entry.name.endsWith('.json')).length;
    if (fileCount >= MAX_PENDING_EVENTS) return false;
    const target = path.join(dir, record.event_id + '.json');
    const temp = target + '.tmp';
    try {
      fs.writeFileSync(temp, JSON.stringify(record), { encoding: 'utf8', flag: 'wx', mode: 0o600 });
      fs.renameSync(temp, target);
      return true;
    } finally {
      try { fs.unlinkSync(temp); } catch { /* success or already cleaned */ }
    }
  } catch {
    // Editor operation must never fail because Nykra is missing or offline.
    return false;
  }
}

function activate(context, options = {}) {
  const vscode = options.vscode || require('vscode');
  const source = 'ide-' + editorId(vscode.env?.appName);
  const started = new WeakMap();
  const output = { recorded: 0, dropped: 0, ignored: 0, version: EXTENSION_VERSION };
  const emit = (tool, outcome, duration_ms, uri) => {
    if (!isTrustedWorkspace(vscode)) { output.ignored++; return; }
    const id = workspaceId(uri || vscode.workspace.workspaceFolders[0].uri);
    if (!id) { output.ignored++; return; }
    const event = {
      event_id: 'ide-' + randomUUID(), source, task_id: id,
      tool, outcome, duration_ms: Math.max(0, duration_ms)
    };
    if (enqueue(event, options)) output.recorded++;
    else output.dropped++;
  };
  context.subscriptions.push(vscode.workspace.onDidSaveTextDocument(document => {
    if (!document || document.uri?.scheme !== 'file') { output.ignored++; return; }
    const folder = vscode.workspace.getWorkspaceFolder(document.uri);
    if (!folder) { output.ignored++; return; }
    emit('document_save', 'succeeded', 0, folder.uri);
  }));
  context.subscriptions.push(vscode.tasks.onDidStartTask(event => {
    if (event && event.execution) started.set(event.execution, performance.now());
  }));
  context.subscriptions.push(vscode.tasks.onDidEndTaskProcess(event => {
    if (!event || !event.execution) return;
    if (typeof event.exitCode !== 'number' || !Number.isInteger(event.exitCode)) { output.ignored++; return; }
    const earlier = started.get(event.execution);
    started.delete(event.execution);
    const elapsed = typeof earlier === 'number' ? performance.now() - earlier : 0;
    const uri = vscode.workspace.workspaceFolders?.[0]?.uri;
    emit('task_completed', event.exitCode === 0 ? 'succeeded' : 'failed', elapsed, uri);
  }));
  return output;
}

function deactivate() {}

module.exports = { activate, deactivate, enqueue, editorId, workspaceId, isTrustedWorkspace };
