import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { scoreItem, searchGroupsFor, termsFor } from "../site/search.mjs";

const payload = JSON.parse(
  readFileSync(new URL("../site/search-index.json", import.meta.url), "utf8"),
);

function resultCount(query) {
  const terms = termsFor(query);
  const groups = searchGroupsFor(terms);
  return payload.items.filter((item) => scoreItem(item, groups, query) > 0).length;
}

function topTitles(query, limit = 10) {
  const terms = termsFor(query);
  const groups = searchGroupsFor(terms);
  return payload.items
    .map((item) => ({ item, score: scoreItem(item, groups, query) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((entry) => entry.item.title);
}

assert.deepEqual(termsFor("의사 수 늘리면 지역의료 좋아지나"), ["의사", "지역의료"]);

const cases = [
  "지역의료",
  "의사 근무시간",
  "평생교육·CPD",
  "CMS-HCC",
  "의료 AI",
  "의사 수 늘리면 지역의료 좋아지나",
  "환자 안전은 어떻게 관리하나",
  "의료사고 예방 알려줘",
  "인공지능이 의료에 미치는 영향",
];

const counts = Object.fromEntries(cases.map((query) => [query, resultCount(query)]));
for (const [query, count] of Object.entries(counts)) {
  assert.ok(count > 0, "expected results for: " + query);
}
assert.equal(resultCount("zzzz검색결과없음zzzz"), 0);
assert.ok(
  topTitles("의사 수 늘리면 지역의료 좋아지나").some((title) => title.includes("지역")),
);
assert.ok(
  topTitles("환자 안전은 어떻게 관리하나").some((title) => title.includes("환자안전")),
);

console.log(JSON.stringify(counts, null, 2));
