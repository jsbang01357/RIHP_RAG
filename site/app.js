import {
  groupRankedResults,
  normalize,
  scoreItem,
  searchGroupsFor,
  termsFor,
} from "./search.mjs";

const COLLECTION_LABELS = {
  "medical-policy-forum": "계간 의료정책포럼",
  "policy-analysis": "정책현안분석",
  "research-report": "연구보고서",
  "issue-briefing": "이슈브리핑",
  "annual-report": "연례보고서",
};

const BOARD_LABELS = {
  annual: "연례보고서",
  policy_analysis: "정책현안·이슈브리핑",
  publication_forum: "계간 의료정책포럼",
  research_report: "연구보고서",
};

const state = {
  items: [],
  query: "",
  collection: "",
  year: "",
  ragRequestId: 0,
  ragController: null,
};

const elements = {
  form: document.querySelector("#searchForm"),
  input: document.querySelector("#searchInput"),
  results: document.querySelector("#results"),
  status: document.querySelector("#resultStatus"),
  clear: document.querySelector("#clearButton"),
  collection: document.querySelector("#collectionFilter"),
  year: document.querySelector("#yearFilter"),
  documentCount: document.querySelector("#documentCount"),
  unitCount: document.querySelector("#unitCount"),
  chunkCount: document.querySelector("#chunkCount"),
  ragAnswer: document.querySelector("#ragAnswer"),
  ragMode: document.querySelector("#ragMode"),
  ragStatus: document.querySelector("#ragStatus"),
  ragText: document.querySelector("#ragText"),
  ragSources: document.querySelector("#ragSources"),
};

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function safeLink(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "rihp.re.kr" ? url.href : "#";
  } catch {
    return "#";
  }
}

function sourceLabel(value) {
  try {
    const url = new URL(value);
    const boardId = url.searchParams.get("bo_table");
    const board = BOARD_LABELS[boardId] || boardId || "게시물";
    const recordId = url.searchParams.get("wr_id");
    return recordId ? `RIHP ${board} #${recordId} 보기 ↗` : "RIHP 게시물 보기 ↗";
  } catch {
    return "RIHP 게시물 보기 ↗";
  }
}

function highlight(value, terms) {
  let output = escapeHtml(value);
  if (!terms.length) return output;
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "giu");
  return output.replace(pattern, "<mark>$1</mark>");
}

function excerptFor(text, terms) {
  const clean = String(text).replace(/\s+/g, " ").trim();
  if (!terms.length) return clean.slice(0, 360);
  const folded = normalize(clean);
  const positions = terms.map((term) => folded.indexOf(term)).filter((position) => position >= 0);
  const first = positions.length ? Math.min(...positions) : 0;
  const start = Math.max(0, first - 110);
  const end = Math.min(clean.length, first + 360);
  return `${start ? "…" : ""}${clean.slice(start, end)}${end < clean.length ? "…" : ""}`;
}

function pageHit(item, terms, searchTerms) {
  const authors = item.authors?.length ? item.authors.join(" · ") : "";
  return `
    <section class="page-hit" aria-label="PDF ${escapeHtml(item.pdf_page)}쪽">
      <div class="page-hit-head">
        <span class="page-number">PDF ${escapeHtml(item.pdf_page)}쪽</span>
        <h4>${highlight(item.title, terms)}</h4>
      </div>
      ${authors ? `<p class="hit-byline">${escapeHtml(authors)}</p>` : ""}
      <p class="excerpt">${highlight(excerptFor(item.text, searchTerms), terms)}</p>
    </section>`;
}

function publicationCard(group, terms, searchTerms) {
  const collection = COLLECTION_LABELS[group.collection] || group.collection;
  const dateLabel = group.publishedAt || group.year;
  const sourceUrl = safeLink(group.sourceUrl);
  const visiblePages = new Set(group.hits.map((hit) => Number(hit.item.pdf_page)));
  const extraPages = group.allPages.filter((page) => !visiblePages.has(page));
  const listedExtraPages = extraPages.slice(0, 12);
  const remainingExtraPages = Math.max(0, extraPages.length - listedExtraPages.length);
  const pageHits = group.hits
    .map((hit) => pageHit(hit.item, terms, searchTerms))
    .join("");
  const extraPageLabel = listedExtraPages.length
    ? `${listedExtraPages.map((page) => `${page}쪽`).join(" · ")}${
        remainingExtraPages ? ` · 외 ${remainingExtraPages}개 페이지` : ""
      }`
    : "";

  return `
    <article class="publication-card">
      <header class="publication-head">
        <div class="publication-heading">
          <div class="result-meta">
            <span class="badge">${escapeHtml(collection)}</span>
            ${dateLabel ? `<span class="badge">${escapeHtml(dateLabel)}</span>` : ""}
            <span class="badge match-badge">관련 PDF ${escapeHtml(group.matchedPageCount)}쪽</span>
          </div>
          <h3>${highlight(group.publicationTitle, terms)}</h3>
          <p class="byline">${escapeHtml(group.publicationId)}</p>
        </div>
        <div class="result-actions">
          <a href="${sourceUrl}" target="_blank" rel="noopener">${escapeHtml(sourceLabel(sourceUrl))}</a>
        </div>
      </header>
      <div class="page-hits">${pageHits}</div>
      ${extraPageLabel ? `<p class="additional-pages"><strong>추가 일치 페이지</strong> ${escapeHtml(extraPageLabel)}</p>` : ""}
    </article>`;
}

function clearRagAnswer() {
  state.ragRequestId += 1;
  state.ragController?.abort();
  state.ragController = null;
  elements.ragAnswer.hidden = true;
  elements.ragStatus.textContent = "";
  elements.ragText.textContent = "";
  elements.ragSources.replaceChildren();
}

function renderRagAnswer(payload) {
  const hybrid = payload.mode === "hybrid";
  elements.ragMode.textContent = hybrid ? "Haystack BM25 + Vertex 의미 검색" : "Haystack BM25 검색";
  elements.ragStatus.textContent = payload.generation_status === "generated"
    ? "공개 발간물의 기계 추출 본문에 근거한 AI 답변입니다."
    : "AI 문장 생성 없이 관련 근거를 우선 표시했습니다.";
  elements.ragText.innerHTML = escapeHtml(payload.answer || "답변을 만들지 못했습니다.")
    .replaceAll("\n", "<br />");
  elements.ragSources.innerHTML = (payload.sources || []).map((source) => {
    const sourceUrl = safeLink(source.source_url);
    const authors = source.authors?.length ? source.authors.join(" · ") : "";
    const excerpt = String(source.content || "").slice(0, 280);
    return `
      <article class="rag-source">
        <div class="rag-source-head">
          <span>[${escapeHtml(source.index)}]</span>
          <strong>PDF ${escapeHtml(source.pdf_page)}쪽</strong>
        </div>
        <h4>${escapeHtml(source.publication_title)}</h4>
        <p class="rag-source-section">${escapeHtml(source.section_title)}${authors ? ` · ${escapeHtml(authors)}` : ""}</p>
        <p>${escapeHtml(excerpt)}${String(source.content || "").length > excerpt.length ? "…" : ""}</p>
        <a href="${sourceUrl}" target="_blank" rel="noopener">${escapeHtml(sourceLabel(sourceUrl))}</a>
      </article>`;
  }).join("");
}

async function requestRagAnswer(query) {
  const trimmed = query.trim();
  if (trimmed.length < 2) {
    clearRagAnswer();
    return;
  }
  state.ragController?.abort();
  const controller = new AbortController();
  state.ragController = controller;
  const requestId = ++state.ragRequestId;
  elements.ragAnswer.hidden = false;
  elements.ragMode.textContent = "Haystack BM25 + Vertex 의미 검색";
  elements.ragStatus.textContent = "관련 발간물을 찾고 근거 답변을 만들고 있습니다…";
  elements.ragText.textContent = "";
  elements.ragSources.replaceChildren();
  try {
    const response = await fetch("/api/rag", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: trimmed, top_k: 6 }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (requestId !== state.ragRequestId) return;
    renderRagAnswer(payload);
  } catch (error) {
    if (controller.signal.aborted || requestId !== state.ragRequestId) return;
    elements.ragStatus.textContent = error.message === "HTTP 429"
      ? "질문이 잠시 몰렸습니다. 잠시 후 다시 시도해 주세요. 아래 본문 검색은 그대로 사용할 수 있습니다."
      : "AI 근거 답변에 연결하지 못했습니다. 아래 브라우저 본문 검색은 그대로 사용할 수 있습니다.";
    elements.ragText.textContent = "";
  }
}

function render() {
  const terms = termsFor(state.query);
  const searchGroups = searchGroupsFor(terms);
  const searchTerms = [...new Set(searchGroups.flat())];
  const fullQuery = normalize(state.query.trim());
  elements.clear.hidden = !state.query && !state.collection && !state.year;

  if (!terms.length && !state.collection && !state.year) {
    elements.status.textContent = "검색어를 입력하거나 위의 추천 키워드를 선택하세요.";
    elements.results.innerHTML = `
      <div class="empty-state">
        <strong>어떤 정책이 궁금한가요?</strong>
        지역의료, 의사인력, 의료교육, 수가, 인공지능처럼 관심 주제를 검색해보세요.
      </div>`;
    return;
  }

  const ranked = state.items
    .filter((item) => !state.collection || item.collection === state.collection)
    .filter((item) => !state.year || item.year === state.year)
    .map((item) => ({
      item,
      score: terms.length ? scoreItem(item, searchGroups, fullQuery) : 1,
    }))
    .filter((entry) => entry.score > 0)
    .sort(
      (a, b) =>
        b.score - a.score ||
        String(b.item.published_at || b.item.year).localeCompare(
          String(a.item.published_at || a.item.year),
        ) ||
        String(b.item.year).localeCompare(String(a.item.year)) ||
        a.item.pdf_page - b.item.pdf_page,
    );

  const publications = groupRankedResults(ranked);
  const matchedPages = publications.reduce(
    (total, publication) => total + publication.matchedPageCount,
    0,
  );

  elements.status.textContent = `${publications.length.toLocaleString("ko-KR")}개 발간물 · ${matchedPages.toLocaleString("ko-KR")}개 관련 PDF 페이지`;
  elements.results.innerHTML = publications.length
    ? publications.map((publication) => publicationCard(publication, terms, searchTerms)).join("")
    : `<div class="empty-state"><strong>일치하는 결과가 없습니다.</strong>검색어를 줄이거나 자료 유형을 전체로 바꿔보세요.</div>`;
}

function updateQuery(value, pushState = true, syncInput = true) {
  const nextQuery = value.trim();
  if (nextQuery !== state.query) clearRagAnswer();
  state.query = nextQuery;
  if (syncInput) elements.input.value = value;
  if (pushState) {
    const url = new URL(window.location.href);
    state.query ? url.searchParams.set("q", state.query) : url.searchParams.delete("q");
    history.replaceState(null, "", url);
  }
  render();
}

function populateFilters() {
  const collections = [...new Set(state.items.map((item) => item.collection))].sort();
  const years = [...new Set(state.items.map((item) => item.year).filter(Boolean))].sort().reverse();
  for (const collection of collections) {
    const option = document.createElement("option");
    option.value = collection;
    option.textContent = COLLECTION_LABELS[collection] || collection;
    elements.collection.append(option);
  }
  for (const year of years) {
    const option = document.createElement("option");
    option.value = year;
    option.textContent = `${year}년`;
    elements.year.append(option);
  }
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  updateQuery(elements.input.value, true, false);
  requestRagAnswer(state.query);
});

let debounce;
let composing = false;
elements.input.addEventListener("compositionstart", () => {
  composing = true;
  window.clearTimeout(debounce);
});
elements.input.addEventListener("compositionend", () => {
  composing = false;
  window.clearTimeout(debounce);
  updateQuery(elements.input.value, true, false);
});
elements.input.addEventListener("input", (event) => {
  if (composing || event.isComposing) return;
  window.clearTimeout(debounce);
  debounce = window.setTimeout(() => updateQuery(elements.input.value, true, false), 140);
});

elements.collection.addEventListener("change", () => {
  state.collection = elements.collection.value;
  render();
});

elements.year.addEventListener("change", () => {
  state.year = elements.year.value;
  render();
});

elements.clear.addEventListener("click", () => {
  state.collection = "";
  state.year = "";
  elements.collection.value = "";
  elements.year.value = "";
  updateQuery("");
});

document.querySelectorAll("[data-query]").forEach((button) => {
  button.addEventListener("click", () => {
    updateQuery(button.dataset.query || "");
    requestRagAnswer(state.query);
    elements.ragAnswer.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key === "/" && document.activeElement !== elements.input) {
    event.preventDefault();
    elements.input.focus();
  }
});

async function boot() {
  try {
    const response = await fetch("./search-index.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.items = payload.items;
    elements.documentCount.textContent = payload.stats.documents.toLocaleString("ko-KR");
    elements.unitCount.textContent = payload.stats.units.toLocaleString("ko-KR");
    elements.chunkCount.textContent = payload.stats.chunks.toLocaleString("ko-KR");
    populateFilters();
    const initialQuery = new URL(window.location.href).searchParams.get("q") || "";
    updateQuery(initialQuery, false);
  } catch (error) {
    elements.status.textContent = "검색 데이터를 불러오지 못했습니다.";
    elements.results.innerHTML = `<div class="empty-state"><strong>데이터 로드 실패</strong>${escapeHtml(error.message)}</div>`;
  }
}

boot();
