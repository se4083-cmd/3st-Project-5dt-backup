import prepared from '../../../data/analytics/prepared-suggestions.json' with { type: 'json' };
import { evidenceSignatureInput, validateGeneratedSuggestions } from './analytics/insights.mjs';
import { sha256 } from './crypto/sha256.mjs';

/** Verify the prepared P1 cache against the exact product, batch, scope and evidence hash. */
export function resolvePreparedSuggestions(bundle) {
  try {
    const key = `${bundle.context.batch_id}|${bundle.context.scope_key}|${bundle.product.product_id}`;
    const entry = prepared.entries[key];
    if (!entry) return null;
    const hash = sha256(evidenceSignatureInput(bundle));
    if (hash !== entry.input_sha256) return null;
    const check = validateGeneratedSuggestions(entry.payload, bundle);
    if (!check.valid) return null;
    return {
      ...check.value, mode:'CHATGPT_PREPARED', mode_label:'사전 작성 AI 제안',
      provenance:entry.provenance, input_sha256:hash, generation_status:'PREPARED_VALIDATED',
    };
  } catch { return null; }
}
