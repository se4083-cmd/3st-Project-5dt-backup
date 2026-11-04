import { reason } from './errors.mjs';

const STATUS_LABELS = Object.freeze({
  RECEIVED: '주문 접수', ORDERED: '주문 접수', PAID: '결제 완료',
  PREPARING: '상품 준비 중', PROCESSING: '상품 준비 중',
  SHIPPED: '배송 시작', IN_TRANSIT: '배송 중', OUT_FOR_DELIVERY: '배송 출발',
  DELIVERED: '배송 완료',
});
const STATIC_TEMPLATES = new Set([
  'V2_RETURN_STEPS_V1', 'V2_EXCHANGE_STEPS_V1', 'V2_TICKET_ANSWER_FAQ_V1', 'V2_ORDER_FREE_INQUIRY_V1',
]);
const TEMPLATE_INTENTS = Object.freeze({
  V2_DELIVERY_STATUS_V1: 'DELIVERY_STATUS', V2_RETURN_STEPS_V1: 'RETURN_STEPS',
  V2_EXCHANGE_STEPS_V1: 'EXCHANGE_STEPS', V2_TICKET_ANSWER_FAQ_V1: 'TICKET_ANSWER_FAQ',
  V2_ORDER_FREE_INQUIRY_V1: 'ORDER_FREE_INQUIRY',
});
export const GENERATION_MODE = 'RETRIEVAL_TEMPLATE';

function unsafeOutput(text) {
  // Additional guard on developer-edited documents. Negative boundary statements
  // remain permitted; positive commitments and injected instructions do not.
  return /(?:환불|보상|배상).{0,16}(?:승인했|승인되었|지급했|지급되었|완료했|완료되었|확정했|확정되었|해드리겠|처리하겠)|(?:계정|제한).{0,16}(?:해제했|해제되었|복구했|복구되었)|\d[\d,]*\s*원|(?:ignore|disregard).{0,30}(?:instruction|rule)|(?:지침|규칙).{0,12}(?:무시|우회)/iu.test(text);
}

export function generateGroundedReply(document, intent, { order } = {}) {
  if (unsafeOutput(document.body)) return { reply: null, reasons: [reason('OUTPUT_POLICY_VIOLATION', '정책 본문에 자동 안내로 허용할 수 없는 약속이나 지시가 포함되어 있습니다.')] };
  if (TEMPLATE_INTENTS[document.template_key] !== intent.intent) return { reply: null, reasons: [reason('TEMPLATE_INTENT_MISMATCH', '등록된 템플릿과 질문군이 일치하지 않습니다.')] };
  if (document.allow_kind !== intent.allowKind || !document.allowed_intents.includes(intent.intent)) {
    return { reply: null, reasons: [reason('TEMPLATE_INTENT_MISMATCH', '검색된 정책과 질문의 허용 안내군이 일치하지 않습니다.')] };
  }
  if (document.order_required && !order) {
    return { reply: null, reasons: [reason('ORDER_REQUIRED', '본인 소유가 확인된 합성 주문을 선택해야 안내를 준비할 수 있습니다.')] };
  }
  if (document.template_key === 'V2_DELIVERY_STATUS_V1' && intent.intent === 'DELIVERY_STATUS') {
    const label = STATUS_LABELS[order?.status];
    if (!label) return { reply: null, reasons: [reason('ORDER_STATUS_UNSUPPORTED', '허용된 현재 배송 상태를 확인할 수 없습니다.')] };
    let etaSentence = '도착 예정일은 아직 확인되지 않았습니다.';
    if (order.eta !== undefined && order.eta !== null && order.eta !== '') {
      // Accept data, never a free-text ETA promise. Calendar dates or UTC ISO only.
      if (typeof order.eta !== 'string' || !/^(?:\d{4}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z)$/u.test(order.eta) || !Number.isFinite(Date.parse(order.eta)) || new Date(order.eta).toISOString().slice(0, 10) !== order.eta.slice(0, 10)) {
        return { reply: null, reasons: [reason('ORDER_ETA_INVALID', '도착 예정일 형식이 유효하지 않아 안내를 보류합니다.')] };
      }
      etaSentence = `조회된 도착 예정일은 ${order.eta.slice(0, 10)}입니다. 이는 현재 조회값이며 도착을 보장하지 않습니다.`;
    }
    const body = document.body.replaceAll('{{status}}', label).replaceAll('{{eta_sentence}}', etaSentence);
    if (body.includes('{{') || body.includes('}}') || !document.body.includes('{{status}}') || !document.body.includes('{{eta_sentence}}')) {
      return { reply: null, reasons: [reason('TEMPLATE_INVALID', '등록된 배송 안내 형식과 일치하지 않습니다.')] };
    }
    return { reply: body, reasons: [] };
  }
  if (STATIC_TEMPLATES.has(document.template_key)) {
    if (document.body.includes('{{') || document.body.includes('}}')) return { reply: null, reasons: [reason('TEMPLATE_INVALID', '정적 안내 문서에 미확정 값이 있습니다.')] };
    return { reply: document.body, reasons: [] };
  }
  return { reply: null, reasons: [reason('TEMPLATE_NOT_REGISTERED', '자동 안내가 허용된 템플릿이 아닙니다.')] };
}
