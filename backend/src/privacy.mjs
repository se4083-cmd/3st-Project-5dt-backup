import { ApiError } from './errors.mjs';
import { validateQuery } from '../../ai/rag/privacy.mjs';

// Reject recognizable contact/payment/identity identifiers before durable writes.
// This intentionally is not advertised as a general PII detector. Use synthetic inputs only.
const prohibited = [
  /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i,
  /(?:^|\D)(?:\+?82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?:\D|$)/,
  /(?:^|\D)\d{6}[- ]?[1-4]\d{6}(?:\D|$)/,
  /(?:^|\D)(?:\d[ -]?){15,19}(?:\D|$)/,
  /(?:비밀번호|password|api[ _-]?key|secret|토큰)\s*[:=]\s*\S+/i,
  /\bsk-[A-Za-z0-9_-]{15,}\b/,
];

export function assertSyntheticInput(value) {
  if (typeof value === 'string') {
    if (value.trim()) {
      try { validateQuery(value); } catch (error) { throw new ApiError(422, error.code ?? 'INVALID_INPUT', error.message); }
    }
    if (prohibited.some((pattern) => pattern.test(value))) {
      throw new ApiError(422, 'SENSITIVE_INPUT_REJECTED', '연락처·개인 식별번호·결제번호·비밀키는 저장하지 않습니다. 합성 예시로 바꿔 주세요.');
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach(assertSyntheticInput);
    return;
  }
  if (value && typeof value === 'object') {
    for (const item of Object.values(value)) assertSyntheticInput(item);
  }
}
