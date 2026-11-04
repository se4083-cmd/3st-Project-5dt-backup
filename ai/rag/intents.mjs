import { normalizeText } from './tokenize.mjs';
import { reason } from './errors.mjs';
import { fullyCoversQuestion } from './scope.mjs';

const CATEGORIES = new Set(['DELIVERY', 'RETURN', 'REFUND', 'PRODUCT', 'PAYMENT', 'ACCOUNT', 'UNKNOWN']);
export const KNOWN_INTENTS = new Set([
  'DELIVERY_STATUS', 'RETURN_STEPS', 'EXCHANGE_STEPS', 'TICKET_ANSWER_FAQ',
  'ORDER_FREE_INQUIRY', 'HUMAN_HANDOFF', 'REFUND_REVIEW', 'COMPENSATION_REVIEW',
  'ACCOUNT_RIGHTS_REVIEW', 'PAYMENT_REVIEW',
]);

export function canonicalCategory(category) {
  if (category === undefined || category === null || category === '') return null;
  if (typeof category !== 'string') return 'UNKNOWN';
  const value = category.toUpperCase();
  if (value === 'SHIPPING') return 'DELIVERY';
  if (value === 'UNCLASSIFIED') return 'UNKNOWN';
  return CATEGORIES.has(value) ? value : 'UNKNOWN';
}

const match = (text, pattern) => pattern.test(text);
const result = (category, intent, allowKind, reasons = [], extra = {}) => ({
  category, intent, allowKind, reasons, orderRequired: ['ORDER_STATUS', 'RETURN_PROCEDURE'].includes(allowKind),
  highRisk: false, humanRequested: false, ...extra,
});

/** Conservative local recognizer, not an LLM confidence score or an external classifier. */
export function recognizeIntent(query) {
  const text = normalizeText(query);
  if (match(text, /(?:지침|규칙|정책|이전\s*명령|시스템\s*메시지).{0,24}(?:무시|우회|잊어|덮어|해제)|(?:ignore|disregard|forget).{0,50}(?:instruction|rule|prompt|previous)|(?:system|developer|assistant)\s*:|<\/?(?:system|assistant|developer)>|(?:프롬프트|시스템\s*명령).{0,24}(?:공개|출력|보여|바꿔)|(?:승인|소유권|인증|권한).{0,16}(?:가정|우회|검사하지|확인하지|생략)/u)) {
    return result('UNKNOWN', null, null, [reason('UNTRUSTED_INSTRUCTION', '문의에 포함된 처리 규칙 변경 지시를 따르지 않고 사람 검토로 넘깁니다.')]);
  }
  if (match(text, /(?:상담사|상담원|담당자|사람|직원).{0,16}(?:연결|통화|대화|상담|처리|확인|바꿔)|(?:연결|통화|대화).{0,12}(?:상담사|상담원|사람)|human\s*(?:agent|support)|talk\s*to\s*(?:a\s*)?(?:human|agent)/u)) {
    return result('ACCOUNT', 'HUMAN_HANDOFF', null, [reason('HUMAN_REQUESTED', '고객의 사람 상담 요청을 우선하여 이관합니다.')], { humanRequested: true });
  }
  if (match(text, /보상|배상|compensat/u)) {
    return result('REFUND', 'COMPENSATION_REVIEW', null, [reason('HIGH_RISK_ACTION', '보상 지급·금액 결정은 사람 검토가 필요합니다.')], { highRisk: true });
  }
  if (match(text, /(?:계정|회원|아이디|로그인|비밀번호|인증|이용\s*제한|정지).{0,30}(?:변경|해제|복구|탈퇴|삭제|정지|초기화|인증|실패|안\s*돼|안\s*되|풀어|바꿔)|(?:해제|복구|탈퇴|삭제).{0,16}(?:계정|회원|제한)|unlock\s*(?:my\s*)?account|reset\s*(?:my\s*)?password/u)) {
    return result('ACCOUNT', 'ACCOUNT_RIGHTS_REVIEW', null, [reason('HIGH_RISK_ACTION', '계정 권리·인증정보 변경은 자동으로 결정하거나 실행하지 않습니다.')], { highRisk: true });
  }
  if (match(text, /환불|refund/u)) {
    const highRisk = match(text, /승인|지급|금액|전액|돌려|보장|확정|해\s*줘|해\s*주|해\s*주세요|해\s*주세요|처리해|당장|지금|approve|pay/u);
    return result('REFUND', 'REFUND_REVIEW', null, [reason(highRisk ? 'HIGH_RISK_ACTION' : 'NOT_ALLOWLISTED', highRisk
      ? '환불 승인·금액·지급 결정은 사람 검토가 필요합니다.'
      : '환불 문의는 현재 개발용 자동 안내 허용군에 포함되지 않아 사람 검토로 넘깁니다.')], { highRisk });
  }
  if (match(text, /결제|청구|카드|payment|chargeback/u)) {
    return result('PAYMENT', 'PAYMENT_REVIEW', null, [reason('NOT_ALLOWLISTED', '결제 문의는 현재 개발용 자동 안내 허용군에 포함되지 않습니다.')]);
  }
  if (match(text, /분쟁|소송|고소|신고|약속|보장|반드시|확실히|도착\s*확정|지연|늦었|늦어|오지\s*않|안\s*왔|안\s*와|아직.{0,10}(?:안|못)|배송.{0,12}(?:취소|주소\s*변경)/u)) {
    const category = match(text, /반품|교환/u) ? 'RETURN' : match(text, /배송|택배|배달|도착|주문/u) ? 'DELIVERY' : 'UNKNOWN';
    return result(category, null, null, [reason('EXCEPTION_REVIEW', '분쟁·예외·일정 보장 요청은 현재 상태 안내만으로 완료하지 않습니다.')]);
  }
  if (match(text, /개봉|사용했|사용한|기한|기간.{0,8}(?:지났|넘었)|예외|불량|파손|고장|훼손|손상|오배송/u)) {
    const category = match(text, /반품|교환/u) ? 'RETURN' : match(text, /상품|제품|물건/u) ? 'PRODUCT' : 'UNKNOWN';
    return result(category, null, null, [reason('EXCEPTION_REVIEW', '상품 상태·기한·예외 판단이 필요한 문의는 사람 검토로 넘깁니다.')]);
  }

  const candidates = [];
  const returnTopic = match(text, /반품|교환|return|exchange/u);
  const stepsQuestion = match(text, /절차|순서|방법|어떻게|어디|안내|신청|접수|steps|process|how/u);
  if (returnTopic && stepsQuestion) {
    const actionText = text.replace(/(?:알려|안내|설명)(?:해)?\s*(?:줘|주|주세요|주십시오|줄래|줄\s*수)/gu, ' ');
    if (match(actionText, /승인|접수\s*해|신청\s*해|처리\s*해|취소\s*해|예약\s*해|(?:반품|교환).{0,10}(?:해\s*줘|해\s*주|해\s*주세요)/u)) {
      return result('RETURN', null, null, [reason('ACTION_REQUIRES_HUMAN', '절차 설명을 넘어 실제 반품·교환 접수나 승인을 요청하여 사람 검토가 필요합니다.')]);
    }
    if (match(text, /반품|return/u)) candidates.push(result('RETURN', 'RETURN_STEPS', 'RETURN_PROCEDURE'));
    if (match(text, /교환|exchange/u)) candidates.push(result('RETURN', 'EXCHANGE_STEPS', 'RETURN_PROCEDURE'));
  }
  if (match(text, /(?:문의|질문|상담).{0,22}(?:답변|진행|상태|결과|확인)|(?:답변|결과).{0,12}(?:어디|확인|볼|보나)|ticket.{0,20}(?:reply|status)/u) &&
      match(text, /어디|확인|조회|방법|볼|보나|진행|상태|답변/u)) {
    candidates.push(result('ACCOUNT', 'TICKET_ANSWER_FAQ', 'GENERAL_FAQ'));
  }
  if (match(text, /주문.{0,16}(?:없이|없어|없을|없는|안\s*했|하지\s*않)|(?:일반\s*문의).{0,15}(?:접수|가능)|without.{0,10}order/u) &&
      match(text, /문의|질문|접수|가능|되나|되나요|돼|해도|inquir/u)) {
    candidates.push(result('ACCOUNT', 'ORDER_FREE_INQUIRY', 'POLICY_GUIDANCE'));
  }
  if (match(text, /배송|택배|배달|도착|(?:내\s*)?주문.{0,16}(?:상태|어디|조회)|shipping|delivery|parcel/u) &&
      match(text, /상태|어디|조회|추적|배송\s*중|언제|도착|오나|오고|오는|왔나|왔는|왔어|진행|status|where|arriv/u) && !returnTopic) {
    candidates.push(result('DELIVERY', 'DELIVERY_STATUS', 'ORDER_STATUS'));
  }
  if (candidates.length === 1) {
    const candidate = candidates[0];
    if (!fullyCoversQuestion(text, candidate.intent)) {
      candidate.reasons.push(reason('UNSUPPORTED_REMAINDER', '질문 전체가 한 가지 허용 안내에 해당하는지 확인되지 않았습니다. 다른 요청이나 미지원 내용까지 사람 검토로 넘깁니다.'));
    }
    return candidate;
  }
  if (candidates.length > 1) return result('UNKNOWN', null, null, [reason('MULTIPLE_INTENTS', '여러 안내 유형이 함께 있어 한 정책으로 자동 완료하지 않습니다.')]);
  let category = 'UNKNOWN';
  if (returnTopic) category = 'RETURN';
  else if (match(text, /배송|택배|배달|도착|주문/u)) category = 'DELIVERY';
  else if (match(text, /상품|제품|물건/u)) category = 'PRODUCT';
  else if (match(text, /계정|회원|로그인/u)) category = 'ACCOUNT';
  return result(category, null, null, [reason('UNKNOWN_INTENT', '사전 정의된 정보 안내 질문으로 확인되지 않아 사람 검토가 필요합니다.')]);
}
