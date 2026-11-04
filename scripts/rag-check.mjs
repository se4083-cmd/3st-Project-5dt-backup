#!/usr/bin/env node
import { inspectKnowledge } from '../ai/rag/maintenance.mjs';

try {
  if (process.argv.length > 2) throw new Error('사용법: npm run rag:check');
  console.log(JSON.stringify(inspectKnowledge(), null, 2));
} catch (error) {
  console.error(JSON.stringify({ valid: false, code: error.code ?? 'RAG_CHECK_FAILED', message: error.message }));
  process.exitCode = 1;
}
