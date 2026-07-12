const COLLECTION_LABELS = {
  "medical-policy-forum": "계간 의료정책포럼",
  "policy-analysis": "정책현안분석",
  "research-report": "연구보고서",
  "issue-briefing": "이슈브리핑",
};

const state = {
  items: [],
  query: "",
  collection: "",
  year: "",
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
};

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const normalize = (value) => String(value || "").normalize("NFC").toLocaleLowerCase("ko");
const termsFor = (query) => [...new Set(normalize(query).split(/\s+/).filter(Boolean))];

function safeLink(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "rihp.re.kr" ? url.href : "#";
  } catch {
    return "#";
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

function scoreItem(item, terms, fullQuery) {
  const title = normalize(item.title);
  const authors = normalize((item.authors || []).join(" "));
  const topics = normalize((item.topics || []).join(" "));
  const text = normalize(item.text);
  const combined = `${title} ${authors} ${topics} ${text}`;
  if (!terms.every((term) => combined.includes(term))) return 0;

  let score = 1;
  for (const term of terms) {
    if (title.includes(term)) score += 60;
    if (authors.includes(term)) score += 28;
    if (topics.includes(term)) score += 18;
    score += Math.min(12, text.split(term).length - 1) * 3;
  }
  if (fullQuery && text.includes(fullQuery)) score += 24;
  return score;
}

function resultCard(item, terms) {
  const collection = COLLECTION_LABELS[item.collection] || item.collection;
  const authors = item.authors?.length ? item.authors.join(" · ") : "저자 정보 확인 중";
  const sourceUrl = safeLink(item.source_url);
  const pdfUrl = safeLink(item.pdf_url);
  return `
    <article class="result-card">
      <div class="result-meta">
        <span class="badge">${escapeHtml(collection)}</span>
        <span class="badge page-badge">PDF p.${escapeHtml(item.pdf_page)}</span>
        ${item.year ? `<span class="badge">${escapeHtml(item.year)}</span>` : ""}
      </div>
      <h3>${highlight(item.title, terms)}</h3>
      <p class="byline">${escapeHtml(authors)} · ${escapeHtml(item.publication_id)}</p>
      <p class="excerpt">${highlight(excerptFor(item.text, terms), terms)}</p>
      <div class="result-actions">
        <a href="${sourceUrl}" target="_blank" rel="noopener noreferrer">RIHP 게시물 ↗</a>
        <a href="${pdfUrl}" target="_blank" rel="noopener noreferrer">원문 PDF ↗</a>
      </div>
    </article>`;
}

function render() {
  const terms = termsFor(state.query);
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
    .map((item) => ({ item, score: terms.length ? scoreItem(item, terms, fullQuery) : 1 }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || a.item.pdf_page - b.item.pdf_page);

  const seen = new Set();
  const deduped = [];
  for (const entry of ranked) {
    const key = `${entry.item.unit_id}:${entry.item.pdf_page}`;
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(entry.item);
    if (deduped.length === 50) break;
  }

  elements.status.textContent = `${deduped.length.toLocaleString("ko-KR")}개의 관련 페이지를 찾았습니다.`;
  elements.results.innerHTML = deduped.length
    ? deduped.map((item) => resultCard(item, terms)).join("")
    : `<div class="empty-state"><strong>일치하는 결과가 없습니다.</strong>검색어를 줄이거나 자료 유형을 전체로 바꿔보세요.</div>`;
}

function updateQuery(value, pushState = true) {
  state.query = value.trim();
  elements.input.value = value;
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
  updateQuery(elements.input.value);
});

let debounce;
elements.input.addEventListener("input", () => {
  window.clearTimeout(debounce);
  debounce = window.setTimeout(() => updateQuery(elements.input.value), 140);
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
    document.querySelector("#results-title").scrollIntoView({ behavior: "smooth" });
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
