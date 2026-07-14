const QUERY_STOPWORDS = new Set([
  "관련",
  "대해",
  "대한",
  "무엇",
  "뭐",
  "어떤",
  "어떻게",
  "알려줘",
  "알려주세요",
  "궁금해",
  "궁금합니다",
  "있나요",
  "있을까",
  "인가요",
  "일까요",
  "되나요",
  "하나",
  "늘리면",
  "늘려야",
  "좋아지나",
]);

const SEARCH_ALIASES = {
  ai: ["인공지능", "artificial intelligence"],
  인공지능: ["ai", "artificial intelligence"],
  의사: ["의사인력", "의료인력", "의사 수"],
  의사부족: ["의사인력", "의료인력", "의사 수"],
  의사증원: ["의사인력", "의대정원", "의사 수"],
  증원: ["의사인력", "의대정원", "정원 확대"],
  의대: ["의과대학", "의학교육", "의대정원"],
  정원: ["의대정원", "의사인력"],
  지방의료: ["지역의료", "지역 의료"],
  지역의료: ["지역 의료"],
  의료사고: ["환자안전", "환자 안전"],
  환자안전: ["의료사고", "환자 안전"],
};

const KOREAN_ENDINGS = [
  "에서는",
  "으로는",
  "에게서",
  "으로",
  "에서",
  "에게",
  "까지",
  "부터",
  "처럼",
  "보다",
  "은",
  "는",
  "이",
  "가",
  "을",
  "를",
  "와",
  "과",
  "에",
  "도",
  "만",
];

export const normalize = (value) =>
  String(value || "").normalize("NFC").toLocaleLowerCase("ko");

function stripKoreanEnding(token) {
  if (!/^[가-힣]+$/u.test(token)) return token;
  for (const ending of KOREAN_ENDINGS) {
    if (token.endsWith(ending) && token.length - ending.length >= 2) {
      return token.slice(0, -ending.length);
    }
  }
  return token;
}

export function termsFor(query) {
  const tokens = normalize(query)
    .replace(/[^\p{L}\p{N}+#.-]+/gu, " ")
    .split(/\s+/)
    .map(stripKoreanEnding)
    .filter((term) => term.length >= 2 && !QUERY_STOPWORDS.has(term));
  return [...new Set(tokens)];
}

export function searchGroupsFor(terms) {
  return terms.map((term) => [...new Set([term, ...(SEARCH_ALIASES[term] || [])])]);
}

function normalizedWords(value) {
  return " " + value.replace(/[^a-z0-9가-힣]+/g, " ") + " ";
}

function includesTerm(value, term) {
  return term === "ai" ? normalizedWords(value).includes(" ai ") : value.includes(term);
}

function occurrences(value, term) {
  if (!includesTerm(value, term)) return 0;
  return term === "ai"
    ? normalizedWords(value).split(" ai ").length - 1
    : value.split(term).length - 1;
}

function textFingerprint(value) {
  return normalize(value).replace(/\s+/g, " ").trim();
}

export function groupRankedResults(ranked, maxPagesPerPublication = 4) {
  const bySource = new Map();

  for (const entry of ranked) {
    const { item, score } = entry;
    let group = bySource.get(item.source_id);
    if (!group) {
      group = {
        sourceId: item.source_id,
        publicationTitle: item.publication_title || item.title,
        publicationId: item.publication_id,
        collection: item.collection,
        year: item.year,
        publishedAt: item.published_at,
        sourceUrl: item.source_url,
        score,
        pageHits: new Map(),
      };
      bySource.set(item.source_id, group);
    }

    group.score = Math.max(group.score, score);
    const pageKey = String(item.pdf_page);
    const existing = group.pageHits.get(pageKey);
    if (!existing || score > existing.score) {
      group.pageHits.set(pageKey, entry);
    }
  }

  return [...bySource.values()]
    .map((group) => {
      const seenText = new Set();
      const uniqueHits = [...group.pageHits.values()]
        .sort(
          (a, b) =>
            b.score - a.score ||
            Number(a.item.pdf_page) - Number(b.item.pdf_page) ||
            String(a.item.id).localeCompare(String(b.item.id)),
        )
        .filter((hit) => {
          const fingerprint = textFingerprint(hit.item.text);
          if (fingerprint.length >= 80 && seenText.has(fingerprint)) return false;
          if (fingerprint.length >= 80) seenText.add(fingerprint);
          return true;
        });
      const { pageHits: _pageHits, ...publication } = group;
      return {
        ...publication,
        matchedPageCount: uniqueHits.length,
        allPages: uniqueHits
          .map((hit) => Number(hit.item.pdf_page))
          .sort((a, b) => a - b),
        hits: uniqueHits.slice(0, maxPagesPerPublication),
      };
    })
    .sort(
      (a, b) =>
        b.score - a.score ||
        String(b.publishedAt || b.year).localeCompare(String(a.publishedAt || a.year)) ||
        a.sourceId.localeCompare(b.sourceId),
    );
}

export function scoreItem(item, groups, fullQuery) {
  if (!groups.length) return 0;

  const title = normalize(item.title);
  const authors = normalize((item.authors || []).join(" "));
  const topics = normalize((item.topics || []).join(" "));
  const text = normalize(item.text);
  const combined = title + " " + authors + " " + topics + " " + text;
  let score = 0;
  let matchedGroups = 0;

  for (const group of groups) {
    let bestVariantScore = 0;
    for (const variant of group) {
      let variantScore = 0;
      if (includesTerm(title, variant)) variantScore += 60;
      if (includesTerm(authors, variant)) variantScore += 28;
      if (includesTerm(topics, variant)) variantScore += 18;
      if (includesTerm(combined, variant)) variantScore += 8;
      variantScore += Math.min(12, occurrences(text, variant)) * 3;
      bestVariantScore = Math.max(bestVariantScore, variantScore);
    }
    if (bestVariantScore > 0) {
      matchedGroups += 1;
      score += bestVariantScore;
    }
  }

  const minimumMatches = Math.min(2, groups.length);
  if (matchedGroups < minimumMatches) return 0;

  score += matchedGroups * 25 + Math.round((matchedGroups / groups.length) * 30);
  const normalizedQuery = normalize(fullQuery);
  if (normalizedQuery && combined.includes(normalizedQuery)) score += 30;
  return score;
}
