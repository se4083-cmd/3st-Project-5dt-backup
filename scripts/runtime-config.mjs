import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

export const projectRoot = fileURLToPath(new URL('..', import.meta.url));
process.chdir(projectRoot);
if (existsSync('.env')) process.loadEnvFile('.env');
if (Number(process.versions.node.split('.')[0]) !== 24) {
  console.error('Node.js 24 LTS를 설치한 뒤 다시 실행해 주세요.');
  process.exit(1);
}
const { values } = parseArgs({ options: { host: { type:'string' }, port: { type:'string' }, strictPort: { type:'boolean' } } });
export const port = Number(values.port || process.env.PORT || 5173);
export const host = values.host || process.env.HOST || '127.0.0.1';
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('PORT는 1~65535의 정수여야 합니다.');
