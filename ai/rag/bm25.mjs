import { tokenize, frequencies } from './tokenize.mjs';

/** Actual BM25 ranking over the current eligible corpus; no scenario lookup. */
export function rankDocuments(query, documents, { limit = 5, k1 = 1.2, b = 0.75 } = {}) {
  if (documents.length === 0) return [];
  const entries = documents.map((document) => {
    const text = `${document.title} ${document.title} ${document.keywords.join(' ')} ${document.body}`;
    const tokens = tokenize(text);
    return { document, length: tokens.length, terms: frequencies(tokens) };
  });
  const averageLength = entries.reduce((sum, entry) => sum + entry.length, 0) / entries.length || 1;
  const documentFrequency = new Map();
  for (const entry of entries) {
    for (const term of entry.terms.keys()) documentFrequency.set(term, (documentFrequency.get(term) ?? 0) + 1);
  }
  // Each query term votes once. Repeating a word 5,000 times cannot inflate its weight.
  const queryTerms = [...new Set(tokenize(query))];
  const scored = entries.map(({ document, length, terms }) => {
    let score = 0;
    let matchedTerms = 0;
    for (const term of queryTerms) {
      const count = terms.get(term) ?? 0;
      if (count === 0) continue;
      matchedTerms += 1;
      const df = documentFrequency.get(term) ?? 0;
      const idf = Math.log(1 + (entries.length - df + 0.5) / (df + 0.5));
      const denominator = count + k1 * (1 - b + b * length / averageLength);
      // Word and bigram matches are both evidence; whole words receive a small boost.
      score += idf * (count * (k1 + 1) / denominator) * (term.startsWith('w:') ? 1.4 : 1);
    }
    return { document, score: Math.round(score * 1e6) / 1e6, matchedTerms };
  });
  return scored.filter((hit) => hit.score > 0 && hit.matchedTerms > 0)
    .sort((a, z) => z.score - a.score || a.document.document_id.localeCompare(z.document.document_id))
    .slice(0, limit);
}
