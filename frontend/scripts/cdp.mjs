// Dependency-free, loopback-only Chromium harness using a fresh disposable profile.
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
export const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
export const assert = (condition, message) => { if (!condition) throw new Error(message); };
export async function chromium() {
  const profile = await mkdtemp('/tmp/csflow-browser-');
  const process = spawn('/usr/bin/chromium', ['--headless', '--no-sandbox', '--disable-dev-shm-usage', '--disable-background-networking', '--disable-component-update', '--disable-sync', '--no-first-run', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore' });
  let ws;
  const close = async () => { ws?.close(); process.kill('SIGTERM'); await new Promise(resolve => process.exitCode !== null ? resolve() : process.once('exit', resolve)); await rm(profile, { recursive: true, force: true }); };
  try {
    let port;
    for (let i = 0; i < 100; i++) { try { port = (await readFile(`${profile}/DevToolsActivePort`, 'utf8')).split('\n')[0]; break; } catch { await delay(50); } }
    assert(port, 'Chromium startup timeout');
    const tab = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
    ws = new WebSocket(tab.webSocketDebuggerUrl); await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
    let sequence = 0; const pending = new Map(), errors = [], responses = [];
    ws.onmessage = event => { const m = JSON.parse(event.data); if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result); } else if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text); else if (m.method === 'Network.responseReceived') responses.push({ path: new URL(m.params.response.url).pathname, status: m.params.response.status }); };
    const call = (method, params = {}) => new Promise((resolve, reject) => { const id = ++sequence; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
    const evaluate = async expression => { const r = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value; };
    const wait = async (expression, name) => { for (let i = 0; i < 160; i++) { if (await evaluate(expression)) return; await delay(50); } throw new Error('Browser timeout: ' + name); };
    const click = label => evaluate(`Array.from(document.querySelectorAll('button,a')).find(b=>b.textContent===${JSON.stringify(label)}).click()`);
    const fill = (selector, value, type = 'HTMLInputElement') => evaluate(`{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(${type}.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));}`);
    const select = (selector, value) => evaluate(`{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));}`);
    const shot = async path => { const r = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); await writeFile(path, Buffer.from(r.data, 'base64')); };
    await call('Page.enable'); await call('Runtime.enable'); await call('Network.enable');
    return { call, evaluate, wait, click, fill, select, shot, errors, responses, close };
  } catch (e) { await close(); throw e; }
}
