import { RagError } from './errors.mjs';

export const MAX_QUERY_CHARACTERS = 10000;

/** Demo input guard. No detector can certify arbitrary free text is non-personal. */
export function validateQuery(query) {
  if (typeof query !== 'string' || query.trim().length === 0) {
    throw new RagError('INVALID_QUERY', '문의는 내용이 있는 텍스트여야 합니다.');
  }
  // Count Unicode code points, not UTF-16 halves. No truncation is performed.
  if ([...query].length > MAX_QUERY_CHARACTERS) {
    throw new RagError('QUERY_TOO_LONG', '문의는 10,000자까지 처리합니다. 내용을 잘라 저장하지 않습니다.');
  }
  if (/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F\u202A-\u202E\u2066-\u2069]/u.test(query)) {
    throw new RagError('INVALID_QUERY_CONTROL', '처리할 수 없는 제어 문자가 포함되어 있습니다.');
  }
  const normalized = query.normalize('NFKC');
  const personalPatterns = [
    /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/iu,
    /(?:^|\D)(?:\+?82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?:\D|$)/u,
    /(?:^|\D)\d{6}[- ]?[1-8]\d{6}(?:\D|$)/u,
    /(?:^|\D)(?:\d[ -]?){13,19}(?:\D|$)/u,
    /(?:비밀번호|인증번호|password|verification\s*code)\s*(?:은|는|:|=)?\s*[A-Za-z0-9!@#$%^&*]{4,}/iu,
    /(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주).{0,30}(?:로|길)\s*\d+(?:[- ]\d+)?/u,
  ];
  if (personalPatterns.some((pattern) => pattern.test(normalized))) {
    throw new RagError('PERSONAL_DATA_NOT_ALLOWED', '개인 연락처·주소·인증정보를 제외한 합성 문의로 실행해 주세요. 입력은 검색하거나 기록하지 않았습니다.');
  }
  return query.trim();
}
