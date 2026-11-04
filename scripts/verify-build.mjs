import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createAppServer } from '../backend/src/server.mjs';

const server = createAppServer({ databasePath: ':memory:' });
server.listen(0, '127.0.0.1');
await once(server, 'listening');
const origin = `http://127.0.0.1:${server.address().port}`;
try {
  const response = await fetch(`${origin}/manager/products`);
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type'), /text\/html/);
  const html = await response.text();
  assert.match(html, /id="root"/);
  const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^\"]+)"/g)].map(match => match[1]);
  assert.ok(assets.length >= 2, 'built JavaScript and stylesheet required');
  for (const path of new Set(assets)) {
    const asset = await fetch(origin + path);
    assert.equal(asset.status, 200, path);
    assert.doesNotMatch(asset.headers.get('content-type'), /text\/html/, path);
    assert.ok((await asset.arrayBuffer()).byteLength > 0, path);
  }
  const status = await fetch(`${origin}/api/status`).then(result => result.json());
  assert.equal(status.api_connected, true);
  assert.equal(status.live_generation_configured, false);
  console.log(`Production bundle verified: SPA route, ${new Set(assets).size} assets, local API status.`);
} finally {
  await server.shutdown();
}
