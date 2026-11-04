import { createServer as createViteServer } from 'vite';
import { createAppServer } from '../backend/src/server.mjs';
import { fileURLToPath } from 'node:url';
import { host, port } from './runtime-config.mjs';
let vite;
const server = createAppServer({
  databasePath: process.env.CSFLOW_DB_PATH,
  frontendMiddleware(req, res, next) {
    if (!vite) { res.writeHead(503); res.end('Starting'); return; }
    vite.middlewares(req, res, next);
  }
});
vite = await createViteServer({
  configFile: fileURLToPath(new URL('../vite.config.ts', import.meta.url)),
  server: { middlewareMode: true, hmr: { server } },
  appType: 'spa'
});
server.on('error', error => {
  console.error(error.code === 'EADDRINUSE' ? `${port} 포트가 사용 중입니다. 기존 실행 창을 닫거나 PORT를 변경해 주세요.` : '서버를 시작할 수 없습니다. 설정을 확인해 주세요.');
  process.exitCode = 1;
  void vite.close();
});
server.listen(port, host, () => console.log(`CS Flow v2 · http://${host}:${port}\n합성 데이터 개발 모드 · Ctrl+C로 종료`));
let stopping = false;
async function shutdown() {
  if (stopping) return;
  stopping = true;
  await vite.close();
  await server.shutdown();
}
process.once('SIGINT', shutdown);
process.once('SIGTERM', shutdown);
