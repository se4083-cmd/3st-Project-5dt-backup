import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createAppServer } from '../backend/src/server.mjs';
import { host, port } from './runtime-config.mjs';
if (!existsSync(new URL('../dist/index.html', import.meta.url))) {
  console.error('먼저 npm run build를 실행해 주세요.');
  process.exit(1);
}
const server = createAppServer({ databasePath: process.env.CSFLOW_DB_PATH });
server.listen(port, host, () => console.log(`CS Flow v2 · http://${host}:${port} · 합성 데이터 개발 모드`));
server.on('error', error => { console.error(`서버 시작 실패 (${error.code || 'ERROR'})`); process.exitCode = 1; });
process.once('SIGINT', () => { void server.shutdown(); });
process.once('SIGTERM', () => { void server.shutdown(); });
