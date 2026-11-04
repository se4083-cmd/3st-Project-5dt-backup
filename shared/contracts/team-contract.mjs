/** Explicit DTO conversion only. This module never authorizes a reply or calls a team API. */
const CATEGORIES = new Set(['DELIVERY', 'RETURN', 'REFUND', 'PRODUCT', 'PAYMENT', 'ACCOUNT', 'UNKNOWN']);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256 = /^[0-9a-f]{64}$/i;

export function toTeamCategory(category) {
  const mapped = category === 'SHIPPING' ? 'DELIVERY' : category === 'UNCLASSIFIED' ? 'UNKNOWN' : category;
  if (!CATEGORIES.has(mapped)) throw new TypeError('UNSUPPORTED_CATEGORY');
  return mapped;
}

export function toStaffCategory(category) {
  const mapped = toTeamCategory(category);
  return mapped === 'UNKNOWN' ? 'UNCLASSIFIED' : mapped;
}

/** The legacy OpenAI function accepts 4,000 characters. Never silently truncate a 10,000-char inquiry. */
export function legacyAnalysisInput(query) {
  if (typeof query !== 'string' || !query.trim() || [...query].length > 10000) throw new TypeError('INVALID_INQUIRY_LENGTH');
  if ([...query].length > 4000) return { status: 'REQUIRES_LONG_INPUT_ADAPTER', query: null, originalLength: [...query].length };
  return { status: 'READY', query, originalLength: [...query].length };
}

export function toEvidenceReference(evidence) {
  if (!evidence || !UUID.test(evidence.documentId) || !Number.isSafeInteger(evidence.version) || evidence.version < 1 ||
      !SHA256.test(evidence.contentHash) || typeof evidence.clauseId !== 'string' || !evidence.clauseId.trim()) {
    throw new TypeError('INVALID_EVIDENCE_REFERENCE');
  }
  return { document_id: evidence.documentId, document_version: evidence.version,
    content_hash: evidence.contentHash, clause_id: evidence.clauseId };
}

/**
 * Future Backend B boundary. allowed is copied only from a separately verified
 * backend decision; retrieval eligibility and review_required cannot approve it.
 * DEMO_ONLY evidence is never advertised as approved production evidence.
 */
export function toBackendBEnvelope(result, { suggestionId, ruleId, backendDecision = null } = {}) {
  if (!UUID.test(suggestionId ?? '') || !UUID.test(ruleId ?? '')) throw new TypeError('TEAM_UUIDS_REQUIRED');
  if (!result || typeof result.reply !== 'string' || !result.reply.trim() || result.reply.length > 10000 ||
      !Array.isArray(result.evidence) || result.evidence.length === 0) throw new TypeError('GROUNDED_DRAFT_REQUIRED');
  const evidenceRefs = result.evidence.map(toEvidenceReference);
  const isDemo = result.scope === 'DEMO_ONLY' || result.evidence.some(evidence => evidence.scope === 'DEMO_ONLY');
  const allowed = !isDemo && result.eligible === true &&
    backendDecision?.authority === 'BACKEND_FINALIZATION_GATE' && backendDecision?.verdict === 'ALLOW' &&
    Number.isSafeInteger(backendDecision.cycle_no) && backendDecision.cycle_no > 0 &&
    Number.isSafeInteger(backendDecision.expected_ticket_version) && backendDecision.expected_ticket_version > 0;
  return {
    draft: result.reply.trim(), allowed, suggestion_id: suggestionId, rule_id: ruleId,
    evidence_refs: evidenceRefs, category: toTeamCategory(result.category),
    prompt_version: result.promptVersion, model_version: result.modelVersion,
    generation_mode: result.generationMode ?? result.mode,
    contract_source: 'V2_MAPPING_ADAPTER_NOT_A_TEAM_API_CALL',
    ...(isDemo ? { blocked_reason: 'DEMO_EVIDENCE_NOT_PRODUCTION_APPROVAL' } : {}),
  };
}
