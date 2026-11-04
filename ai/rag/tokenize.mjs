/** Dependency-free lexical retrieval: Korean word tokens plus character bigrams. */
const STOP_WORDS = new Set([
  '알려', '알려줘', '알려주세요', '주세요', '부탁', '부탁해요', '부탁합니다',
  '저는', '제가', '있나요', '있어요', '하나요', '해주세요', '어떻게', '정말',
  '있습니다', '합니다', '수', '및',
  'please', 'the', 'and', 'is', 'a', 'an', 'to', 'for', 'of', 'in', 'my', 'can', 'you',
]);

const KOREAN_SUFFIXES = ['으로', '에서', '에게', '하는', '하신', '하며', '하면', '해서', '하기', '할', '를', '을', '가', '이', '은', '는', '와', '과', '도', '에', '의', '로'];

function lexicalWord(word) {
  if (!/^[\p{Script=Hangul}]+$/u.test(word)) return word;
  for (const suffix of KOREAN_SUFFIXES) {
    if (word.endsWith(suffix) && [...word].length - [...suffix].length >= 2) return word.slice(0, -suffix.length);
  }
  return word;
}

export function normalizeText(text) {
  return text.normalize('NFKC').toLocaleLowerCase('en-US').replace(/\s+/gu, ' ').trim();
}

export function tokenize(text) {
  const normalized = normalizeText(text);
  const words = normalized.match(/[\p{Script=Hangul}\p{Letter}\p{Number}]+/gu) ?? [];
  const tokens = [];
  for (const rawWord of words) {
    if (STOP_WORDS.has(rawWord)) continue;
    const word = lexicalWord(rawWord);
    tokens.push(`w:${word}`);
    // Bigrams retrieve inflected Korean words without an external tokenizer.
    if (/[\p{Script=Hangul}]/u.test(word)) {
      const chars = [...word];
      for (let i = 0; i + 1 < chars.length; i += 1) tokens.push(`b:${chars[i]}${chars[i + 1]}`);
    }
  }
  return tokens;
}

export function frequencies(tokens) {
  const counts = new Map();
  for (const token of tokens) counts.set(token, (counts.get(token) ?? 0) + 1);
  return counts;
}
