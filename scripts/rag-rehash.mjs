#!/usr/bin/env node
import { refreshDocument } from '../ai/rag/maintenance.mjs';

try {
  if (process.argv.length !== 3) throw new Error('사용법: npm run rag:rehash -- policies/return-steps.json');
  console.log(JSON.stringify(refreshDocument(process.argv[2]), null, 2));
} catch (error) {
  console.error(JSON.stringify({ valid: false, code: error.code ?? 'RAG_REFRESH_FAILED', message: error.message }));
  process.exitCode = 1;
}
