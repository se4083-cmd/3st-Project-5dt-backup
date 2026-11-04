/**
 * Full-input coverage for the small local allowlist. A recognized keyword does
 * not cover an unrelated second request. Every lexical unit must be explainable
 * by the chosen information intent and these finite Korean question forms.
 * Uncovered words are never returned or logged; they can contain personal data.
 */
const COMMON = [
  '안녕하세요', '안녕', '혹시', '저', '제', '내', '우리', '지금', '현재', '오늘',
  '좀', '한번', '한', '번', '어디', '언제', '어떤', '무엇', '어떻게',
  '알려', '안내', '설명', '궁금', '부탁', '싶', '확인', '조회', '방법', '가능',
  '볼', '보', '보는', '알', '대해', '관련', '자세', '구체적', '감사', '그럼',
  '이', '그', '것', '건', '곳', '수', '있', '없', '안', '못', '잘', '내용',
  '그리고', '또', '또는', '혹은',
];

const ENDINGS = [
  '가', '이', '은', '는', '을', '를', '의', '도', '와', '과', '랑', '에', '에서', '서',
  '에게', '으로', '로', '만', '까지', '부터', '이나', '나', '보다', '처럼', '씩', '쯤',
  '중', '중인', '인지', '요', '인가요', '나요', '하나요', '하나', '해요', '합니다',
  '습니까', '습니까요', '습니다', '해', '해주세요', '해줘', '줘', '주', '주세요',
  '주시겠어요', '주시겠습니까', '주시면', '줄래요', '줄래', '줄', '있나요', '있을까요',
  '됩니까', '됩니다', '되나요', '되요', '되죠', '하죠', '할까요', '했나요', '세요',
  '할', '하는', '하고', '하면', '하려면', '해서', '한', '했', '해도', '할수', '하다',
  '한가요', '게', '히', '해주', '고', '는데', '데', '인', '않', '지', '더',
];

const INTENT_WORDS = Object.freeze({
  DELIVERY_STATUS: ['배송', '택배', '배달', '주문', '상태', '도착', '예정', '예정일', '일자', '일정', '진행', '추적', '위치', '왔', '오', '오는', '왔는', '왔나', '배송중'],
  RETURN_STEPS: ['반품', '신청', '접수', '절차', '순서', '주문', '상세', '상품', '제품', '요청'],
  EXCHANGE_STEPS: ['교환', '신청', '접수', '절차', '순서', '주문', '상세', '상품', '제품', '요청'],
  TICKET_ANSWER_FAQ: ['문의', '질문', '상담', '접수', '답변', '진행', '상태', '결과', '상세', '내문의'],
  ORDER_FREE_INQUIRY: ['주문', '일반', '문의', '질문', '상담', '접수', '없이', '아직', '선택', '해도', '되', '돼', '하지'],
});

const ENGLISH_WORDS = Object.freeze({
  DELIVERY_STATUS: ['where', 'is', 'my', 'the', 'parcel', 'delivery', 'shipping', 'status', 'arriving', 'arrive', 'please'],
  RETURN_STEPS: ['how', 'to', 'request', 'a', 'return', 'process', 'steps', 'please'],
  EXCHANGE_STEPS: ['how', 'to', 'request', 'an', 'exchange', 'process', 'steps', 'please'],
  TICKET_ANSWER_FAQ: ['where', 'is', 'my', 'ticket', 'reply', 'status', 'please'],
  ORDER_FREE_INQUIRY: ['can', 'i', 'submit', 'an', 'inquiry', 'without', 'an', 'order', 'please'],
});

function coveredWord(word, dictionary, lengths) {
  const reachable = new Uint8Array(word.length + 1);
  reachable[0] = 1;
  for (let end = 1; end <= word.length; end += 1) {
    for (const length of lengths) {
      const start = end - length;
      if (start >= 0 && reachable[start] && dictionary.has(word.slice(start, end))) {
        reachable[end] = 1;
        break;
      }
    }
  }
  return reachable[word.length] === 1;
}

export function fullyCoversQuestion(text, intent) {
  const intentWords = INTENT_WORDS[intent];
  if (!intentWords) return false;
  const dictionary = new Set([...COMMON, ...ENDINGS, ...intentWords]);
  const lengths = [...new Set([...dictionary].map((word) => word.length))].sort((a, b) => a - b);
  const english = new Set(ENGLISH_WORDS[intent] ?? []);
  const words = text.match(/[\p{Letter}\p{Number}]+/gu) ?? [];
  return words.length > 0 && words.every((word) => {
    if (/^[\p{Script=Hangul}]+$/u.test(word)) return coveredWord(word, dictionary, lengths);
    return english.has(word);
  });
}
