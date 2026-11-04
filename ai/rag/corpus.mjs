import { readFileSync, realpathSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { RagError, reason } from './errors.mjs';
import { KNOWN_INTENTS } from './intents.mjs';

export const DEFAULT_CORPUS_DIR = fileURLToPath(new URL('../../data/rag/', import.meta.url));
export const CORPUS_SCHEMA = 'csflow.rag.corpus.v1';
export const DOCUMENT_SCHEMA = 'csflow.rag.document.v1';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu;
const HASH = /^[0-9a-f]{64}$/u;
const TOPICS = new Set(['DELIVERY', 'RETURN', 'REFUND', 'PRODUCT', 'PAYMENT', 'ACCOUNT']);
const ALLOW_KINDS = new Set(['ORDER_STATUS', 'GENERAL_FAQ', 'RETURN_PROCEDURE', 'POLICY_GUIDANCE']);
const SAFE_KEY = /^[A-Z0-9][A-Z0-9_-]{0,79}$/u;

export const hashText = (value) => createHash('sha256').update(value, 'utf8').digest('hex');
export const clone = (value) => structuredClone(value);

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  return value;
}

export const hashObject = (value) => hashText(JSON.stringify(stable(value)));

export function validNow(value = Date.now()) {
  const milliseconds = value instanceof Date ? value.getTime() : typeof value === 'string' ? Date.parse(value) : value;
  if (typeof milliseconds !== 'number' || !Number.isFinite(milliseconds)) {
    throw new RagError('INVALID_TIME', '검증 기준 시각이 유효하지 않습니다.');
  }
  return milliseconds;
}

function fail(code, document = '') {
  throw new RagError(code, '지식 문서 검증에 실패했습니다. 정책 파일을 확인해 주세요.', document ? { document } : {});
}

function parseJson(path, code) {
  try { return JSON.parse(readFileSync(path, 'utf8')); }
  catch { throw new RagError(code, '지식 문서 파일을 읽거나 해석할 수 없습니다.'); }
}

export function validateDocument(document) {
  if (!document || typeof document !== 'object' || Array.isArray(document)) fail('INVALID_DOCUMENT');
  const key = typeof document.policy_key === 'string' && SAFE_KEY.test(document.policy_key) ? document.policy_key : '';
  if (document.schema_version !== DOCUMENT_SCHEMA || document.scope !== 'DEMO_ONLY' ||
      document.source !== 'V2_ISOLATED_SYNTHETIC_POLICY' || !UUID.test(document.document_id ?? '') ||
      !key || !Number.isSafeInteger(document.version) || document.version < 1 ||
      typeof document.active !== 'boolean' ||
      !['DEMO_ONLY', 'DRAFT_REQUIRES_TEAM_REVIEW', 'UNAPPROVED'].includes(document.approval_status)) fail('INVALID_DOCUMENT_SCHEMA', key);
  if (typeof document.title !== 'string' || document.title.trim().length === 0 || document.title.length > 200 ||
      typeof document.body !== 'string' || document.body.trim().length === 0 || document.body.length > 20000 ||
      !HASH.test(document.content_hash ?? '') || hashText(document.body) !== document.content_hash) fail('DOCUMENT_HASH_MISMATCH', key);
  if (!Array.isArray(document.allowed_topics) || document.allowed_topics.length !== 1 || !TOPICS.has(document.allowed_topics[0]) ||
      !Array.isArray(document.allowed_intents) || document.allowed_intents.length === 0 ||
      document.allowed_intents.some((intent) => !KNOWN_INTENTS.has(intent)) ||
      !Array.isArray(document.keywords) || document.keywords.length > 60 ||
      document.keywords.some((word) => typeof word !== 'string' || word.length < 1 || word.length > 100) ||
      (document.allow_kind !== null && !ALLOW_KINDS.has(document.allow_kind)) ||
      typeof document.order_required !== 'boolean' || !SAFE_KEY.test(document.clause_id ?? '') ||
      !SAFE_KEY.test(document.template_key ?? '')) fail('INVALID_DOCUMENT_RULES', key);
  const from = Date.parse(document.effective_from);
  const to = document.effective_to === null ? Infinity : Date.parse(document.effective_to);
  if (!Number.isFinite(from) || !(to === Infinity || Number.isFinite(to)) || from >= to) fail('INVALID_DOCUMENT_DATES', key);
  return document;
}

export function documentUsability(document, now) {
  if (!document.active) return reason('DOCUMENT_INACTIVE', '정책이 비활성 상태입니다.');
  if (document.approval_status !== 'DEMO_ONLY') return reason('DOCUMENT_UNAPPROVED', '개발 시연 사용이 지정되지 않은 정책입니다.');
  if (Date.parse(document.effective_from) > now) return reason('DOCUMENT_NOT_EFFECTIVE', '아직 효력이 시작되지 않은 정책입니다.');
  if (document.effective_to !== null && Date.parse(document.effective_to) <= now) return reason('DOCUMENT_EXPIRED', '효력이 종료된 정책입니다.');
  return null;
}

/** Read on each request: edits, withdrawals, and effective-date changes are observable. */
export function loadCorpus(corpusDir = DEFAULT_CORPUS_DIR, suppliedNow = Date.now()) {
  const now = validNow(suppliedNow);
  let root;
  try { root = realpathSync(corpusDir); } catch { fail('CORPUS_UNAVAILABLE'); }
  const manifest = parseJson(resolve(root, 'manifest.json'), 'CORPUS_MANIFEST_INVALID');
  if (manifest.schema_version !== CORPUS_SCHEMA || manifest.scope !== 'DEMO_ONLY' ||
      typeof manifest.corpus_id !== 'string' || !Number.isSafeInteger(manifest.revision) || manifest.revision < 1 ||
      !Array.isArray(manifest.files) || manifest.files.length < 1 || manifest.files.length > 100 ||
      new Set(manifest.files).size !== manifest.files.length) fail('CORPUS_MANIFEST_INVALID');
  const ids = new Set(); const keys = new Set(); const clauses = new Set();
  const documents = manifest.files.map((file) => {
    if (typeof file !== 'string' || !/^policies\/[a-z0-9_-]+\.json$/u.test(file)) fail('CORPUS_PATH_INVALID');
    let path;
    try { path = realpathSync(resolve(root, file)); } catch { fail('CORPUS_FILE_MISSING'); }
    if (!path.startsWith(`${root}${sep}`)) fail('CORPUS_PATH_INVALID');
    const document = validateDocument(parseJson(path, 'DOCUMENT_JSON_INVALID'));
    if (ids.has(document.document_id) || keys.has(document.policy_key) || clauses.has(document.clause_id)) fail('DOCUMENT_ID_COLLISION');
    ids.add(document.document_id); keys.add(document.policy_key); clauses.add(document.clause_id);
    return document;
  });
  // Includes metadata as well as text. Changing eligibility changes corpusVersion.
  const fingerprint = hashObject({ manifest, documents });
  const corpusVersion = `${manifest.corpus_id}:r${manifest.revision}:${fingerprint.slice(0, 16)}`;
  const activeDocuments = documents.filter((document) => documentUsability(document, now) === null);
  return { manifest, documents, activeDocuments, corpusVersion, fingerprint, now };
}

export function toEvidence(document, score = null) {
  return {
    documentId: document.document_id, policyKey: document.policy_key,
    version: document.version, contentHash: document.content_hash,
    clauseId: document.clause_id, title: document.title, text: document.body,
    active: document.active, source: document.source, scope: document.scope,
    approvalStatus: document.approval_status, templateKey: document.template_key,
    category: document.allowed_topics[0], allowKind: document.allow_kind,
    orderRequired: document.order_required, effectiveFrom: document.effective_from,
    effectiveTo: document.effective_to, score,
  };
}

export function checkEvidence(evidence, corpus, { expectedCorpusVersion } = {}) {
  const reasons = [];
  if (!Array.isArray(evidence) || evidence.length < 1 || evidence.length > 5) {
    return { valid: false, reasons: [reason('EVIDENCE_MISSING', '현재 문서 근거가 필요합니다.')], corpusVersion: corpus.corpusVersion };
  }
  if (expectedCorpusVersion && expectedCorpusVersion !== corpus.corpusVersion) {
    reasons.push(reason('CORPUS_CHANGED', '초안 준비 이후 지식 문서 구성이 변경되었습니다.'));
  }
  const seen = new Set();
  for (const reference of evidence) {
    const id = reference?.documentId ?? reference?.document_id;
    if (seen.has(id)) { reasons.push(reason('DUPLICATE_EVIDENCE', '같은 근거가 중복되었습니다.')); continue; }
    seen.add(id);
    const document = corpus.documents.find((item) => item.document_id === id);
    if (!document) { reasons.push(reason('EVIDENCE_NOT_FOUND', '현재 지식 묶음에서 근거 문서를 찾을 수 없습니다.')); continue; }
    const unusable = documentUsability(document, corpus.now);
    if (unusable) reasons.push(unusable);
    const hash = reference.contentHash ?? reference.content_hash;
    const clause = reference.clauseId ?? reference.clause_id;
    if (reference.version !== document.version || hash !== document.content_hash || clause !== document.clause_id ||
        (reference.templateKey !== undefined && reference.templateKey !== document.template_key) ||
        (reference.text !== undefined && reference.text !== document.body) ||
        (reference.source !== undefined && reference.source !== document.source) ||
        (reference.scope !== undefined && reference.scope !== document.scope)) {
      reasons.push(reason('EVIDENCE_CHANGED', '문서 버전·해시·조항 또는 본문이 현재 근거와 다릅니다.'));
    }
  }
  return { valid: reasons.length === 0, reasons, corpusVersion: corpus.corpusVersion };
}
