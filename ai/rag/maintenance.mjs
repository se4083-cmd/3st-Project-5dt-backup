import { cpSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { isAbsolute, join, relative, resolve } from 'node:path';
import { DEFAULT_CORPUS_DIR, hashText, loadCorpus, validateDocument } from './corpus.mjs';
import { RagError } from './errors.mjs';

export function inspectKnowledge({ corpusDir = DEFAULT_CORPUS_DIR, now } = {}) {
  const corpus = loadCorpus(corpusDir, now);
  return {
    valid: true, scope: 'DEMO_ONLY', corpusVersion: corpus.corpusVersion,
    documentCount: corpus.documents.length, activeCount: corpus.activeDocuments.length,
    documents: corpus.documents.map((document) => ({
      documentId: document.document_id, policyKey: document.policy_key, version: document.version,
      contentHash: document.content_hash, active: document.active, approvalStatus: document.approval_status,
    })),
  };
}

/** Explicit, one-file authoring command. It never activates or approves a policy. */
export function refreshDocument(argument, { corpusDir = DEFAULT_CORPUS_DIR, now } = {}) {
  if (typeof argument !== 'string' || argument.trim().length === 0) {
    throw new RagError('POLICY_FILE_REQUIRED', '수정한 정책 파일 하나를 지정해 주세요.');
  }
  const root = realpathSync(corpusDir);
  let file = argument.replaceAll('\\', '/');
  if (isAbsolute(file)) file = relative(root, realpathSync(file)).replaceAll('\\', '/');
  if (file.startsWith('data/rag/')) file = file.slice('data/rag/'.length);
  if (!/^policies\/[a-z0-9_-]+\.json$/u.test(file)) throw new RagError('POLICY_FILE_INVALID', 'policies 폴더의 JSON 파일 하나만 지정할 수 있습니다.');
  const manifestPath = resolve(root, 'manifest.json');
  const originalManifest = readFileSync(manifestPath, 'utf8');
  const manifest = JSON.parse(originalManifest);
  if (!Array.isArray(manifest.files) || !manifest.files.includes(file) || !Number.isSafeInteger(manifest.revision) || manifest.revision < 1) {
    throw new RagError('POLICY_FILE_UNREGISTERED', 'manifest에 등록된 정책 파일만 갱신할 수 있습니다.');
  }
  const targetPath = resolve(root, file);
  if (realpathSync(targetPath) !== targetPath) throw new RagError('POLICY_FILE_INVALID', '다른 파일을 가리키는 링크는 갱신할 수 없습니다.');
  const originalDocument = readFileSync(targetPath, 'utf8');
  const document = JSON.parse(originalDocument);
  if (typeof document.body !== 'string' || !Number.isSafeInteger(document.version) || document.version < 1) {
    throw new RagError('INVALID_DOCUMENT_SCHEMA', '본문과 현재 버전을 확인해 주세요.');
  }
  const priorVersion = document.version;
  document.version += 1;
  document.content_hash = hashText(document.body);
  manifest.revision += 1;
  validateDocument(document);
  const nextDocument = `${JSON.stringify(document, null, 2)}\n`;
  const nextManifest = `${JSON.stringify(manifest, null, 2)}\n`;
  const temporary = mkdtempSync(join(tmpdir(), 'csflow-rag-validate-'));
  let checked;
  try {
    cpSync(root, temporary, { recursive: true });
    writeFileSync(resolve(temporary, file), nextDocument);
    writeFileSync(resolve(temporary, 'manifest.json'), nextManifest);
    checked = inspectKnowledge({ corpusDir: temporary, now });
  } finally { rmSync(temporary, { recursive: true, force: true }); }
  // Never overwrite a policy someone else edited while this command validated it.
  if (readFileSync(targetPath, 'utf8') !== originalDocument || readFileSync(manifestPath, 'utf8') !== originalManifest) {
    throw new RagError('POLICY_CHANGED_DURING_REFRESH', '검증 중 파일이 변경되어 저장하지 않았습니다. 다시 확인해 주세요.');
  }
  try {
    writeFileSync(targetPath, nextDocument);
    writeFileSync(manifestPath, nextManifest);
  } catch (error) {
    writeFileSync(targetPath, originalDocument);
    writeFileSync(manifestPath, originalManifest);
    throw error;
  }
  return {
    ...checked, changedFile: file, documentId: document.document_id,
    previousVersion: priorVersion, version: document.version,
    contentHash: document.content_hash, manifestRevision: manifest.revision,
    active: document.active, approvalStatus: document.approval_status,
  };
}
