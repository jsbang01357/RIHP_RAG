import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../site/index.html", import.meta.url), "utf8");
const app = readFileSync(new URL("../site/app.js", import.meta.url), "utf8");

for (const marker of ["id=\"ragAnswer\"", "id=\"ragSources\"", "HAYSTACK HYBRID RAG", "class=\"sidebar\"", "data-view=\"archive\"", "data-view-panel=\"downloads\""]) {
  assert.ok(html.includes(marker), `HTML 누락: ${marker}`);
}
for (const marker of ["fetch(\"/api/rag\"", "requestRagAnswer", "generation_status", "source_url", "function setView", "popstate"]) {
  assert.ok(app.includes(marker), `앱 연결 누락: ${marker}`);
}

console.log("OK: Haystack RAG 답변 · RIHP 근거 링크 화면 연결 검증 완료");
