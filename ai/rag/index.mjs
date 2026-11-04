import { loadCorpus, checkEvidence, toEvidence, hashText, DEFAULT_CORPUS_DIR } from './corpus.mjs';
import { rankDocuments } from './bm25.mjs';
import { recognizeIntent, canonicalCategory } from './intents.mjs';
import { validateQuery } from './privacy.mjs';
import { generateGroundedReply, GENERATION_MODE } from './generator.mjs';
import { RagError, reason } from './errors.mjs';

export const RAG_SCHEMA_VERSION = 'csflow.rag.result.v1';
export const RETRIEVAL_MODE = 'LOCAL_BM25';
export { RagError, canonicalCategory };

export const SAMPLE_QUERIES = Object.freeze([
  { query: '택배가 지금 어디쯤 왔나요?', needsOrder: true, expectedCategory: 'DELIVERY', expectedRoute: 'AUTO_CANDIDATE' },
  { query: '반품 신청은 어떤 순서로 하나요?', needsOrder: true, expectedCategory: 'RETURN', expectedRoute: 'AUTO_CANDIDATE' },
  { query: '교환 신청 방법을 알려 주세요.', needsOrder: true, expectedCategory: 'RETURN', expectedRoute: 'AUTO_CANDIDATE' },
  { query: '내 문의 답변은 어디서 확인해요?', needsOrder: false, expectedCategory: 'ACCOUNT', expectedRoute: 'AUTO_CANDIDATE' },
  { query: '주문 없이 문의해도 되나요?', needsOrder: false, expectedCategory: 'ACCOUNT', expectedRoute: 'AUTO_CANDIDATE' },
  { query: '지금 환불 승인해 주세요.', needsOrder: true, expectedCategory: 'REFUND', expectedRoute: 'HUMAN' },
  { query: '보상금을 확정해 주세요.', needsOrder: false, expectedCategory: 'REFUND', expectedRoute: 'HUMAN' },
  { query: '계정 이용 제한을 해제해 주세요.', needsOrder: false, expectedCategory: 'ACCOUNT', expectedRoute: 'HUMAN' },
]);

function knownError(error) {
  return error instanceof RagError ? reason(error.code, error.message)
    : reason('RAG_UNAVAILABLE', '지식 검색을 완료하지 못해 사람 검토가 필요합니다.');
}

function hitView(hit) {
  return { ...toEvidence(hit.document, hit.score), matchedTerms: hit.matchedTerms };
}

function baseAnswer() {
  return {
    schemaVersion: RAG_SCHEMA_VERSION, category: 'UNKNOWN', intent: null, allowKind: null,
    eligible: false, reply: null, reasons: [], evidence: [], templateKey: null,
    mode: GENERATION_MODE, generationMode: GENERATION_MODE, modelVersion: 'NONE',
    promptVersion: 'local-retrieval-template-v1', corpusVersion: null,
    scope: 'DEMO_ONLY', orderRequired: false, highRisk: false, humanRequested: false,
    retrieval: { mode: RETRIEVAL_MODE, hits: [], queryLength: 0, queryHash: null },
  };
}

/**
 * Stable local provider boundary. `eligible` means a grounded draft is ready.
 * It does NOT authorize automatic finalization, order access, or external action.
 */
export function createRagProvider({ corpusDir = DEFAULT_CORPUS_DIR, now: configuredNow } = {}) {
  const clock = (now) => now ?? (typeof configuredNow === 'function' ? configuredNow() : configuredNow) ?? Date.now();

  function search(query, options = {}) {
    const text = validateQuery(query);
    const corpus = loadCorpus(corpusDir, clock(options.now));
    const category = canonicalCategory(options.category);
    if (options.limit !== undefined && (!Number.isSafeInteger(options.limit) || options.limit < 1 || options.limit > 10)) {
      throw new RagError('INVALID_SEARCH_LIMIT', '검색 건수는 1~10 사이의 정수여야 합니다.');
    }
    const documents = category && category !== 'UNKNOWN'
      ? corpus.activeDocuments.filter((document) => document.allowed_topics.includes(category))
      : corpus.activeDocuments;
    const hits = rankDocuments(text, documents, { limit: options.limit ?? 5 }).map(hitView);
    return {
      schemaVersion: RAG_SCHEMA_VERSION, mode: RETRIEVAL_MODE, scope: 'DEMO_ONLY',
      corpusVersion: corpus.corpusVersion, documentCount: corpus.documents.length,
      activeCount: corpus.activeDocuments.length, queryLength: [...text].length,
      queryHash: hashText(text), hits,
    };
  }

  function answer(query, context = {}) {
    const output = baseAnswer();
    let text; let corpus;
    try {
      text = validateQuery(query);
    } catch (error) {
      output.reasons = [knownError(error)];
      return output;
    }
    // Keep the validated input fingerprint even if the corpus is unavailable, so
    // the backend can record a HUMAN handoff without inventing policy evidence.
    output.retrieval.queryLength = [...text].length;
    output.retrieval.queryHash = hashText(text);
    try {
      corpus = loadCorpus(corpusDir, clock(context.now));
    } catch (error) {
      output.corpusVersion = 'UNAVAILABLE';
      output.reasons = [knownError(error)];
      return output;
    }
    const intent = recognizeIntent(text);
    Object.assign(output, {
      category: intent.category, intent: intent.intent, allowKind: intent.allowKind,
      orderRequired: intent.orderRequired, highRisk: intent.highRisk, humanRequested: intent.humanRequested,
      corpusVersion: corpus.corpusVersion, reasons: [...intent.reasons],
    });
    const suppliedCategory = canonicalCategory(context.category);
    if (suppliedCategory && (suppliedCategory === 'UNKNOWN' || suppliedCategory !== intent.category)) {
      output.reasons.push(reason('CATEGORY_MISMATCH', '요청에 제공된 분류와 현재 질문의 허용 분류가 일치하지 않습니다.'));
    }
    // Retrieval is query-driven. Policy IDs and scenario IDs never select a result.
    const documents = intent.category === 'UNKNOWN' ? corpus.activeDocuments
      : corpus.activeDocuments.filter((document) => document.allowed_topics.includes(intent.category));
    const hits = rankDocuments(text, documents, { limit: 5 });
    output.retrieval = {
      mode: RETRIEVAL_MODE, hits: hits.map(hitView), queryLength: [...text].length,
      queryHash: hashText(text), documentCount: corpus.documents.length, activeCount: corpus.activeDocuments.length,
    };
    const matches = hits.filter(({ document }) => intent.intent && document.allowed_intents.includes(intent.intent));
    const applicablePolicies = documents.filter((document) => intent.intent && document.allowed_intents.includes(intent.intent));
    if (applicablePolicies.length > 1) {
      output.reasons.push(reason('POLICY_CONFLICT', '같은 질문군에 유효한 정책이 여러 개여서 자동 답변을 결정하지 않습니다.'));
      output.evidence = matches.map(hitView);
      return output;
    }
    if (matches.length === 0) {
      if (intent.intent) output.reasons.push(reason('POLICY_NOT_FOUND', '질문에 일치하는 유효한 정책 근거를 찾지 못했습니다.'));
      return output;
    }
    const selected = matches[0];
    output.evidence = [hitView(selected)];
    output.templateKey = selected.document.template_key;
    if (output.reasons.length > 0 || !intent.allowKind) return output;
    if (selected.document.allow_kind !== intent.allowKind || selected.document.order_required !== intent.orderRequired) {
      output.reasons.push(reason('POLICY_RULE_MISMATCH', '검색된 정책과 현재 허용 규칙이 일치하지 않습니다.'));
      return output;
    }
    const generated = generateGroundedReply(selected.document, intent, context);
    output.reply = generated.reply;
    output.reasons.push(...generated.reasons);
    const evidenceValidation = checkEvidence(output.evidence, corpus);
    output.reasons.push(...evidenceValidation.reasons);
    output.eligible = typeof output.reply === 'string' && output.reply.trim().length > 0 && output.reasons.length === 0;
    return output;
  }

  function ask({ query, ...context } = {}) { return answer(query, context); }

  function validateEvidence(evidence, options = {}) {
    try {
      const corpus = loadCorpus(corpusDir, clock(options.now));
      return checkEvidence(evidence, corpus, options);
    } catch (error) {
      return { valid: false, reasons: [knownError(error)], corpusVersion: null };
    }
  }

  function knowledge(options = {}) {
    const corpus = loadCorpus(corpusDir, clock(options.now));
    const usable = new Set(corpus.activeDocuments.map((document) => document.document_id));
    return {
      schemaVersion: RAG_SCHEMA_VERSION, corpusSchemaVersion: corpus.manifest.schema_version,
      corpusVersion: corpus.corpusVersion, scope: 'DEMO_ONLY', mode: RETRIEVAL_MODE,
      generationMode: GENERATION_MODE, modelVersion: 'NONE',
      documentCount: corpus.documents.length, activeCount: corpus.activeDocuments.length,
      documents: corpus.documents.map((document) => ({
        ...toEvidence(document), usable: usable.has(document.document_id),
        allowedIntents: [...document.allowed_intents],
      })),
      sampleQueries: structuredClone(SAMPLE_QUERIES),
    };
  }

  return Object.freeze({ mode: RETRIEVAL_MODE, generationMode: GENERATION_MODE, search, answer, ask, askRag: ask, knowledge, validateEvidence });
}

const defaultProvider = createRagProvider();
export const search = (query, options) => defaultProvider.search(query, options);
export const answer = (query, context) => defaultProvider.answer(query, context);
export const askRag = (input) => defaultProvider.ask(input);
export const knowledge = (options) => defaultProvider.knowledge(options);
export const validateEvidence = (evidence, options) => defaultProvider.validateEvidence(evidence, options);
export default defaultProvider;
