import { createServer } from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { RuntimeRepository } from './repository.mjs';
import { OperationsService, customerTickets } from './operations-service.mjs';
import { demoPrincipal, requireOwnedTicket, requireRole } from './identity.mjs';
import { ApiError } from './errors.mjs';
import { getCustomerView, deriveMetrics } from '../../shared/operations/engine.mjs';
import { createRagProvider } from '../../ai/rag/index.mjs';
import { getProductOperations } from './product-operations.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.pdf': 'application/pdf' };

function json(res, status, value) {
  const body = JSON.stringify(value);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
}

async function body(req) {
  if (!/^application\/json(?:\s*;|$)/i.test(req.headers['content-type'] ?? '')) {
    throw new ApiError(415, 'JSON_REQUIRED', 'application/json 본문을 사용해 주세요.');
  }
  const chunks = [];
  let bytes = 0;
  for await (const chunk of req) {
    bytes += chunk.length;
    if (bytes > 131072) throw new ApiError(413, 'BODY_TOO_LARGE', '요청 본문이 너무 큽니다. 문의는 10,000자 이하로 입력해 주세요.');
    chunks.push(chunk);
  }
  let parsed;
  try { parsed = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { throw new ApiError(400, 'INVALID_JSON', 'JSON 요청 형식을 확인해 주세요.'); }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new ApiError(400, 'INVALID_JSON_OBJECT', 'JSON 객체를 전달해 주세요.');
  return parsed;
}

function checkOrigin(req) {
  if (req.method !== 'POST' && req.method !== 'PUT' && req.method !== 'PATCH' && req.method !== 'DELETE') return;
  if (!req.headers.origin) return;
  try { if (new URL(req.headers.origin).host === req.headers.host) return; } catch { /* fail closed */ }
  throw new ApiError(403, 'CROSS_ORIGIN_REJECTED', '현재 앱 화면에서 실행한 요청만 허용합니다.');
}

function runtime(provider) {
  return { mode: 'LOCAL_SYNTHETIC_REFERENCE', storage: 'SQLITE_LOCAL', apiVersion: 'v2.1',
    rag: 'LOCAL_BM25_RETRIEVAL_TEMPLATE', model: 'NONE', authentication: 'DEMO_ROLE_HEADERS',
    externalDelivery: false, productionBackendConnected: false, live_generation_configured: false };
}

function staticResponse(req, res, directory) {
  if (!['GET', 'HEAD'].includes(req.method)) return json(res, 405, { error: { code: 'METHOD_NOT_ALLOWED', message: '지원하지 않는 요청 방식입니다.' } });
  let pathname;
  try { pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname); } catch { return json(res, 400, { error: { code: 'INVALID_PATH', message: '경로 형식을 확인해 주세요.' } }); }
  const requested = resolve(directory, `.${pathname}`);
  if (requested !== directory && !requested.startsWith(directory + sep)) return json(res, 404, { error: { code: 'NOT_FOUND', message: '파일을 찾을 수 없습니다.' } });
  const file = existsSync(requested) && statSync(requested).isFile() ? requested : resolve(directory, 'index.html');
  if (!existsSync(file)) return json(res, 404, { error: { code: 'FRONTEND_NOT_BUILT', message: 'npm run build 후 npm start로 실행해 주세요. 개발 중에는 npm run dev를 사용하세요.' } });
  res.writeHead(200, { 'Content-Type': MIME[extname(file)] ?? 'application/octet-stream', 'X-Content-Type-Options': 'nosniff',
    'Cache-Control': extname(file) === '.html' ? 'no-cache' : 'public, max-age=3600' });
  if (req.method === 'HEAD') return res.end();
  createReadStream(file).on('error', () => res.destroy()).pipe(res);
}

/** One HTTP server for the Vite middleware in dev and built files in production. */
export function createAppServer({ databasePath = resolve(ROOT, '.local/runtime.sqlite'), frontendMiddleware,
  staticDirectory = resolve(ROOT, 'dist'), clock = Date.now, ragProvider = createRagProvider() } = {}) {
  const repository = new RuntimeRepository({ databasePath, clock });
  const service = new OperationsService(repository, ragProvider);
  const server = createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      const path = url.pathname.replace(/\/$/, '') || '/';
      if (!path.startsWith('/api/')) {
        const fallback = (error) => error ? json(res, 500, { error: { code: 'FRONTEND_FAILED', message: '화면을 불러오지 못했습니다.' } }) : staticResponse(req, res, staticDirectory);
        if (frontendMiddleware) return frontendMiddleware(req, res, fallback);
        return fallback();
      }
      checkOrigin(req);
      if (path === '/api/status' && req.method === 'GET') {
        return json(res, 200, { ok: true, ...runtime(ragProvider), runtime: runtime(ragProvider),
          api_connected: true, live_generation_configured: false, model_configured: false,
          prepared_insights_available: true, version: '2.1.0', synthetic_only: true });
      }
      const principal = demoPrincipal(req.headers);
      if (path === '/api/v2/identity' && req.method === 'GET') return json(res, 200, { principal, authentication: 'LOCAL_DEMO_ONLY' });
      if (path === '/api/v2/state' && req.method === 'GET') {
        requireRole(principal, ['admin', 'agent']);
        const { state, revision } = repository.read();
        return json(res, 200, { state, revision, runtime: runtime(ragProvider) });
      }
      if (path === '/api/v2/customer' && req.method === 'GET') {
        const { state, revision } = repository.read();
        return json(res, 200, { tickets: customerTickets(state, principal), revision });
      }
      if (path.startsWith('/api/v2/customer/') && req.method === 'GET') {
        const id = decodeURIComponent(path.slice('/api/v2/customer/'.length));
        const { state, revision } = repository.read();
        // Public projection is scoped to the selected synthetic customer even for demo staff.
        requireOwnedTicket(state, id, { ...principal, role: 'customer' });
        return json(res, 200, { ticket: getCustomerView(state, id), revision });
      }
      if (path === '/api/v2/orders' && req.method === 'GET') {
        return json(res, 200, { orders: repository.orders(principal.customerRef).map(({ customerRef, ...order }) => order), revision: repository.read().revision });
      }
      if ((path === '/api/v2/rag/documents' || path === '/api/v2/rag/knowledge') && req.method === 'GET') {
        requireRole(principal, ['admin', 'agent']);
        return json(res, 200, { knowledge: ragProvider.knowledge({ now: clock() }), runtime: runtime(ragProvider) });
      }
      if (path === '/api/v2/metrics' && req.method === 'GET') {
        requireRole(principal, ['admin', 'agent']);
        const { state, revision } = repository.read();
        return json(res, 200, { metrics: deriveMetrics(state, clock()), revision, source: 'LOCAL_SYNTHETIC_OPERATION_LEDGER' });
      }
      const productOperations = path.match(/^\/api\/v2\/products\/([^/]+)\/operations$/);
      if (productOperations && req.method === 'GET') {
        requireRole(principal, ['admin', 'agent']);
        const { state, revision } = repository.read();
        return json(res, 200, getProductOperations(state, revision, decodeURIComponent(productOperations[1])));
      }
      if (path === '/api/v2/actions' && req.method === 'POST') return json(res, 200, await service.action(await body(req), principal));
      if (path === '/api/v2/rag/ask' && req.method === 'POST') return json(res, 200, await service.ask(await body(req), principal));
      return json(res, 404, { error: { code: 'API_NOT_FOUND', message: '지원하는 로컬 API 경로를 확인해 주세요.' } });
    } catch (error) {
      if (res.headersSent || res.destroyed) { res.destroy(); return; }
      const known = error instanceof ApiError;
      const busy = error.code === 'ERR_SQLITE_ERROR' && /busy|locked/i.test(error.message);
      let revision = null;
      try { if (!repository.closed) revision = repository.read().revision; } catch { /* the error response must not require a healthy store */ }
      json(res, known ? error.status : busy ? 503 : 500, { error: { code: known ? error.code : busy ? 'STORE_BUSY' : 'INTERNAL_ERROR',
        message: known ? error.message : busy ? '저장소가 다른 작업을 처리 중입니다. 같은 요청으로 결과를 다시 확인해 주세요.' : '요청을 처리하지 못했습니다. 입력 원문은 로그에 기록하지 않았습니다.' },
        ...(known ? error.details : {}), revision });
    }
  });
  server.repository = repository;
  server.service = service;
  server.on('close', () => repository.close());
  server.shutdown = () => new Promise((resolveClose, reject) => {
    if (!server.listening) { repository.close(); resolveClose(); return; }
    server.close((error) => error ? reject(error) : resolveClose());
    server.closeIdleConnections();
  });
  return server;
}
